#!/usr/bin/env python3
"""One-step, command-only intervention in a reconstructed music checkpoint."""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE=Path(sys.argv[1]); OUT=BASE/'counterfactual-results'; OUT.mkdir(exist_ok=True)
cfg=json.loads((BASE/'counterfactual-plan.json').read_text())
prefix='diverge-cf-'+os.environ['SLURM_JOB_ID']
names=[prefix+'-setup',prefix+'-control',prefix+'-intervention']
snapshot=prefix+':checkpoint'

def cmd(args,input=None,check=True,timeout=120):
    return subprocess.run(args,input=input,text=True,stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,timeout=timeout,check=check)

def docker(*args,**kw):return cmd(['docker',*args],**kw)
def save(name,data):(OUT/name).write_text(json.dumps(data,indent=2))

def main():
    save('design.json',dict(**cfg,scope='one next model response; no generated commands executed',
         limitations=['reconstructed checkpoint, not an archived intermediate container snapshot',
         'fixed seed single sample per arm; outcome does not establish full-task rescue',
         '8192 output-token cap; length termination is censored',
         'Bonsai analysis/plan retained; only commands and their actual observations replaced']))
    try:
        docker('run','-d','--name',names[0],'--hostname',cfg['hostname'],'--cpus=1','--memory=2g',
               '--workdir=/app',cfg['base_image'],'sleep','infinity')
        install=docker('exec',names[0],'python3','-m','pip','install','pypdf==6.19.0')
        (OUT/'install.log').write_text(install.stdout)
        for c in cfg['setup_commands']:
            r=docker('exec','-i',names[0],'bash',input=c['keystrokes'],check=False)
            with (OUT/'setup.log').open('a') as f:f.write(r.stdout)
        inventory=docker('exec',names[0],'bash','-c','sha256sum /app/Harmony.pdf; python3 --version; pip freeze; sha256sum /tmp/examine.py')
        (OUT/'checkpoint-inventory.txt').write_text(inventory.stdout)
        save('base-image.json',json.loads(docker('image','inspect',cfg['base_image']).stdout))
        docker('commit',names[0],snapshot)
        request=json.loads(Path(cfg['request_path']).read_text())
        for arm in ['control','intervention']:
            name=names[1 if arm=='control' else 2]
            docker('run','-d','--name',name,'--hostname',cfg['hostname'],'--network=none',
                   '--cpus=1','--memory=2g','--workdir=/app',snapshot,'sleep','infinity')
            action=dict(cfg['bonsai_action'])
            if arm=='intervention':action['commands']=cfg['fp16_action']['commands']
            transcript=[]
            for c in action['commands']:
                r=docker('exec','-i',name,'bash',input=c['keystrokes'],check=False)
                transcript.append(dict(command=c['keystrokes'],returncode=r.returncode,output=r.stdout))
            save(arm+'-execution.json',transcript)
            observation='New Terminal Output:\n\n'+''.join(
                'root@'+cfg['hostname']+':/app# '+r['command']+r['output']+'\n' for r in transcript)
            messages=request['messages']+[
                dict(role='assistant',content=json.dumps(action)),dict(role='user',content=observation)]
            body=dict(model='local',messages=messages,temperature=1.0,seed=1,max_tokens=8192)
            save(arm+'-request.json',body)
            req=urllib.request.Request('http://127.0.0.1:8203/v1/chat/completions',
                    json.dumps(body).encode(),{'Content-Type':'application/json'})
            started=time.time()
            with urllib.request.urlopen(req,timeout=600) as f:response=json.load(f)
            save(arm+'-response.json',response)
            print(json.dumps(dict(arm=arm,latency_s=time.time()-started,usage=response.get('usage'),
                    finish_reason=response['choices'][0]['finish_reason'])),flush=True)
        save('finished.json',dict(finished=True,timestamp=time.time()))
    finally:
        docker('rm','-f',*names,check=False)
        docker('image','rm',snapshot,check=False)

if __name__=='__main__':main()
