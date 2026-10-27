import concurrent.futures, datetime, fcntl, hashlib, json, os, queue, signal, threading, time, traceback, shutil, subprocess, sys
from pathlib import Path
from core import DEFAULT, SYSTEM, atomic, parse_action
from runtime import Model, docker, http, action_text
from trial import Trial, STOP, TERMINAL
from rubrics import OVERNIGHT_TASKS
from verify import config, verify
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
RUN=ROOT/'runs'/'oct04-eight-new-tools'
CUTOFF=datetime.datetime(2026,10,5,14,tzinfo=datetime.timezone.utc).timestamp()
JOB=os.environ['SLURM_JOB_ID']
NAMES=[]

def physical_gpus():
    result=[]
    for x in os.environ['SLURM_JOB_GPUS'].split(','):
        if '-' in x and not x.startswith('GPU-'):
            a,b=map(int,x.split('-'));result.extend(map(str,range(a,b+1)))
        else:result.append(x)
    assert len(result)==4,result
    return result

def start_server(lane,gpu):
    kind='qwen' if lane<3 else 'bonsai'
    port=20000+(int(JOB)%3000)*5+lane
    name=f'tbv2-{JOB}-server-{lane}';NAMES.append(name)
    model='Qwen3.8-27B-F16.gguf' if kind=='qwen' else 'Ternary-Bonsai-2-27B-PTQ1_0.gguf'
    binary=BASE/'src_p215/build/bin'
    docker('run','-d','--name',name,'--label',f'tbv2.job={JOB}','--gpus','device='+gpu,
           '--cpus','8','--memory','72g' if kind=='qwen' else '32g','--network','host',
           '-v',str(BASE)+':'+str(BASE)+':ro','-e','LD_LIBRARY_PATH='+str(binary),
           '--entrypoint',str(binary/'llama-server'),'ml_benchmark:latest',
           '-m',str(BASE/'models'/model),'-ngl','99','-fa','on','-c','65536','--parallel','1',
           '--port',str(port),'--host','127.0.0.1','--seed','1','--reasoning-preserve','-t','8')
    return dict(lane=lane,kind=kind,gpu=gpu,port=port,name=name,model_file=model)

def readiness(server):
    url='http://127.0.0.1:'+str(server['port'])
    for _ in range(240):
        if STOP.is_set():raise RuntimeError('Allocation stopping')
        state=docker('inspect','-f','{{.State.Running}}',server['name'])['output'].strip()
        if state!='true':raise RuntimeError('Server stopped: '+server['name'])
        try:
            if http(url+'/health',timeout=5).get('status')=='ok':break
        except Exception:pass
        time.sleep(5)
    else:raise RuntimeError('Server startup incomplete')
    model=Model(url)
    messages=[{'role':'system','content':SYSTEM},{'role':'user','content':(ROOT/'tasks/wal-recovery-ordering/instruction.md').read_text()}]
    prompt,ids=model.tokens(messages)
    response=model.generate(messages,4096,1,DEFAULT['sampling'])
    atomic(RUN/f'canary-{server["lane"]}.json',dict(input_tokens=len(ids),response=response))
    assert response['usage']['prompt_tokens']==len(ids),(server,response['usage'],len(ids))
    assert response['choices'][0]['finish_reason']!='length',server
    parse_action(action_text(response['choices'][0]['message']))
    return model

def monitor():
    while not STOP.wait(15):
        rows=[]
        for path in sorted(RUN.glob('*/state.json')):
            s=json.loads(path.read_text());rows.append({k:s.get(k) for k in ['id','task','status','turn','generated_tokens','usage_valid']})
        atomic(RUN/'status.json',dict(job=JOB,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),cutoff_utc='2026-10-05T14:00:00Z',attempts=rows))
        for name in list(NAMES):
            log=docker('logs','--tail','200',name,check=False)
            (RUN/(name+'.log')).write_text(log['output'])
        if time.time()>=CUTOFF-600:STOP.set()

def worker(server,model,tasks,images):
    while not STOP.is_set():
        try:task=tasks.get_nowait()
        except queue.Empty:return
        ident=server['kind']+'-'+task
        cfg=dict(DEFAULT,seed=DEFAULT['seed']+OVERNIGHT_TASKS.index(task)*1000)
        try:
            trial=Trial(RUN,ident,task,model,cfg,images[task]['environment']['id'],JOB,
                        (ROOT/'tasks'/task/'instruction.md').read_text(),config(task)['artifacts'])
            atomic(trial.root/'assignment.json',server)
            state=trial.run()
            print('TRIAL',ident,state['status'],state['turn'],state['generated_tokens'],flush=True)
        except Exception:
            atomic(RUN/(ident+'-controller-error.json'),dict(error=traceback.format_exc()))
        finally:tasks.task_done()

def reports(images):
    results={}
    for kind in ['qwen','bonsai']:
        for task in OVERNIGHT_TASKS:
            path=RUN/(kind+'-'+task)
            if not (path/'artifacts/manifest.json').exists():continue
            if time.time()>=CUTOFF-600:return
            try:
                result=verify(task,path/'artifacts',path/'verification',JOB,images)
                baseline=json.loads((ROOT/'preflight'/task/'baseline/verification/evaluation.json').read_text())
                result['baseline_score']=baseline['score']
                before={g['group']:g for g in baseline['score']['groups']}
                result['regressed_groups']=[g['group'] for g in result['score']['groups'] if g['upper']<before[g['group']]['lower']]
                result['improved_groups']=[g['group'] for g in result['score']['groups'] if g['lower']>before[g['group']]['upper']]
                result['improvement_bounds']=[result['score']['lower']-baseline['score']['upper'],result['score']['upper']-baseline['score']['lower']]
                results[kind+'-'+task]=result
                atomic(RUN/'functional-results.json',results)
                # Reference and private tests are placed only in review packets,
                # after model execution, outside all agent environments.
                alias=hashlib.sha256(('private-review-oct04-'+kind+'-'+task).encode()).hexdigest()[:12]
                packet=RUN/'review'/alias;packet.mkdir(parents=True,exist_ok=True)
                shutil.copytree(path/'turns',packet/'turns',dirs_exist_ok=True)
                shutil.copytree(path/'artifacts',packet/'artifacts',dirs_exist_ok=True,symlinks=True)
                (packet/'artifacts/manifest.json').unlink(missing_ok=True)
                atomic(RUN/'review-identities'/(alias+'.json'),dict(model=kind,task=task))
                atomic(packet/'index.json',dict(task=task,trajectory='turns/',artifacts='artifacts/',reference=str(ROOT/'tasks'/task/'solution'),tests=str(ROOT/'tasks'/task/'tests'),functional=result,process_review='pending independent frontier review',rubric=['requirement understanding','evidence gathering','hypothesis and decision quality','tool use and implementation','verification and recovery'],scoring='Score each dimension 0-4 with cited turn IDs; separate uncertainty from errors. Do not reward plausible prose without supporting actions.'))
            except Exception:atomic(path/'verification-error.json',dict(error=traceback.format_exc()))

def main():
    RUN.mkdir(parents=True,exist_ok=True)
    lock=(RUN/'lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    signal.signal(signal.SIGTERM,lambda *a:STOP.set())
    signal.signal(signal.SIGINT,lambda *a:STOP.set())
    if time.time()>=CUTOFF-900:raise RuntimeError('Authorized allocation window has ended')
    images=json.loads((ROOT/'images.json').read_text())
    atomic(RUN/'manifest.json',dict(job=JOB,tasks=OVERNIGHT_TASKS,config=DEFAULT,cutoff_utc='2026-10-05T14:00:00Z',code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.py')},images=images,protocol='custom common harness v2; not official TB leaderboard scores'))
    subprocess.run([sys.executable,'-m','unittest','-v','test_harness'],check=True)
    subprocess.run([sys.executable,'integration.py'],check=True)
    gpus=physical_gpus()
    servers=[start_server(i,gpus[i if i<3 else 3]) for i in range(5)]
    atomic(RUN/'servers.json',servers)
    threading.Thread(target=monitor,daemon=True).start()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            models=list(ex.map(readiness,servers))
        print('ALL FIVE SERVERS READY; CANARIES PASSED',flush=True)
        while not (ROOT/'preflight.json').exists():
            if STOP.wait(10):raise RuntimeError('Allocation stopped during preflight')
        preflight=json.loads((ROOT/'preflight.json').read_text())
        for task in OVERNIGHT_TASKS:
            ref=preflight[task]['reference']
            if ref['status']!='verified' or ref['score']['lower']!=100:
                raise RuntimeError('Unresolved reference verification: '+task)
        queues={k:queue.Queue() for k in ['qwen','bonsai']}
        for q in queues.values():
            for t in OVERNIGHT_TASKS:q.put(t)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures=[ex.submit(worker,s,m,queues[s['kind']],images) for s,m in zip(servers,models)]
            for f in futures:f.result()
    finally:
        for name in list(NAMES):
            (RUN/(name+'.log')).write_text(docker('logs',name,check=False)['output'])
            docker('rm','-f',name,check=False);NAMES.remove(name)
    reports(images)
    atomic(RUN/'controller-finished.json',dict(job=JOB,paused=STOP.is_set()))

if __name__=='__main__':main()
