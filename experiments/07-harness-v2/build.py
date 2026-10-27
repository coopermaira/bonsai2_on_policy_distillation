import concurrent.futures, hashlib, json, os, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
TASKS=['wal-recovery-ordering','risk-scorer-replay','html-js-filter','rs-archive-clone','bun-sourcemap-leak','production-planning','sound-change-cascade','cargo-flight-dispatch']
def build(pair):
    task,kind=pair
    tag=f'cmaira/tbv2-{task}-{kind}:20261004'
    log=ROOT/'build-logs'/f'{task}-{kind}.log';log.parent.mkdir(exist_ok=True)
    with log.open('w') as f:
        subprocess.run(['docker','build','--cpu-period=100000','--cpu-quota=400000','--memory=8g','-t',tag,str(ROOT/'tasks'/task/kind)],stdout=f,stderr=subprocess.STDOUT,check=True)
    info=json.loads(subprocess.check_output(['docker','image','inspect',tag]))[0]
    if info['Config'].get('Volumes'):raise RuntimeError('Uncheckpointed image volumes: '+tag)
    return task,kind,{'tag':tag,'id':info['Id'],'user':info['Config'].get('User',''),'workdir':info['Config'].get('WorkingDir','')}
if __name__=='__main__':
    images={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for task,kind,info in ex.map(build,[(t,k) for t in TASKS for k in ['environment','tests']]):
            images.setdefault(task,{})[kind]=info
            print(task,kind,info['id'],flush=True)
            (ROOT/'images.json').write_text(json.dumps(images,indent=2))
    sources={}
    for t in TASKS:
        sources[t]={str(p.relative_to(ROOT/'tasks'/t)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'tasks'/t).rglob('*')) if p.is_file()}
    (ROOT/'source-hashes.json').write_text(json.dumps(sources,indent=2))
