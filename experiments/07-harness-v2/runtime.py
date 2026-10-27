import json, os, shlex, shutil, subprocess, time, urllib.request
from pathlib import Path
from core import InfrastructureError, atomic

def command(args,check=True,input=None):
    p=subprocess.run(list(map(str,args)),input=input,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if check and p.returncode:raise InfrastructureError(f'{args}: {p.returncode}\n{p.stdout[-6000:]}')
    return dict(code=p.returncode,output=p.stdout)

def docker(*args,**kw):return command(['docker',*args],**kw)

def http(url,data=None,timeout=3600):
    req=urllib.request.Request(url,None if data is None else json.dumps(data).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

TOOLS=[{'type':'function','function':{'name':'act','description':'Take one terminal-task action. Supply exactly one of command, wait, recall, or done. Optionally update the durable memory notebook.','parameters':{'type':'object','properties':{'command':{'type':'string'},'wait':{'type':'boolean'},'done':{'type':'boolean'},'recall':{'type':'object','properties':{'turn':{'type':'integer'},'offset':{'type':'integer'},'limit':{'type':'integer'}},'required':['turn']},'memory':{'type':'string'},'analysis':{'type':'string'},'plan':{'type':'string'}},'additionalProperties':False}}}]

def action_text(msg):
    calls=msg.get('tool_calls') or []
    if calls:
        if len(calls)!=1 or calls[0].get('function',{}).get('name')!='act':raise ValueError('Exactly one act tool call is required')
        args=calls[0]['function']['arguments']
        return args if isinstance(args,str) else json.dumps(args)
    return msg.get('content') or ''

class Model:
    def __init__(self,url):self.url=url
    def tokens(self,messages):
        prompt=http(self.url+'/apply-template',{'messages':messages,'tools':TOOLS,'parallel_tool_calls':False})['prompt']
        ids=http(self.url+'/tokenize',{'content':prompt,'add_special':True,'parse_special':True})['tokens']
        return prompt,ids
    def count(self,messages):return len(self.tokens(messages)[1])
    def generate(self,messages,cap,seed,sampling):
        return http(self.url+'/v1/chat/completions',dict(model='local',messages=messages,max_tokens=cap,
                    seed=seed,cache_prompt=True,tools=TOOLS,parallel_tool_calls=False,**sampling))

WRAPPER=r'''#!/bin/bash
mkdir -p /tmp/.tbv2-shell
if [ -f /tmp/.tbv2-shell/environment ]; then source /tmp/.tbv2-shell/environment; fi
readonly TBV2_INTERNAL_BASE=/tmp/.tbv2-shell
readonly TBV2_INTERNAL_ID="$1"
if [ -f "$TBV2_INTERNAL_BASE/cwd" ]; then cd -- "$(cat "$TBV2_INTERNAL_BASE/cwd")" || exit 125; fi
echo "$$" > "$TBV2_INTERNAL_BASE/$TBV2_INTERNAL_ID.pid"
tbv2_finish() {
    local tbv2_code=$?
    pwd > "$TBV2_INTERNAL_BASE/cwd"
    export -p > "$TBV2_INTERNAL_BASE/environment"
    printf '%s\n' "$tbv2_code" > "$TBV2_INTERNAL_BASE/$TBV2_INTERNAL_ID.done.tmp"
    mv "$TBV2_INTERNAL_BASE/$TBV2_INTERNAL_ID.done.tmp" "$TBV2_INTERNAL_BASE/$TBV2_INTERNAL_ID.done"
}
trap tbv2_finish EXIT
source "$TBV2_INTERNAL_BASE/$TBV2_INTERNAL_ID.sh"
'''

class Box:
    def __init__(self,name,job,root):self.name=name;self.job=job;self.root=Path(root)
    def start(self,image,cpus=4,memory='8g'):
        docker('run','-d','--name',self.name,'--label',f'tbv2.job={self.job}',
               '--cpus',cpus,'--memory',memory,'--pids-limit','512','--network','bridge',
               '--security-opt','no-new-privileges:true','--entrypoint','sleep',image,'infinity')
        wrapper=self.root/'shell-wrapper.sh';wrapper.write_text(WRAPPER)
        docker('cp',wrapper,self.name+':/tmp/tbv2-shell-wrapper.sh')
        docker('exec',self.name,'bash','-c','mkdir -p /tmp/.tbv2-shell')
    def remove(self):docker('rm','-f',self.name,check=False)
    def snapshot(self,tag):return docker('commit',self.name,tag)['output'].strip().splitlines()[-1]
    def launch(self,script,ident):
        path=self.root/(ident+'.sh');path.write_text(script+'\n')
        docker('cp',path,self.name+':/tmp/.tbv2-shell/'+ident+'.sh')
        dest='/tmp/.tbv2-shell/'+ident
        shell=f'exec bash /tmp/tbv2-shell-wrapper.sh {shlex.quote(ident)} > {shlex.quote(dest+".out")} 2>&1'
        docker('exec','-d',self.name,'bash','-c',shell)
    def poll(self,ident,delay=1):
        time.sleep(delay)
        script='''import json,os
from pathlib import Path
p=Path('/tmp/.tbv2-shell')/os.environ['TBV2_COMMAND']
done=Path(str(p)+'.done');out=Path(str(p)+'.out');pid=Path(str(p)+'.pid')
n=out.stat().st_size if out.exists() else 0
text=''
if out.exists():
 with out.open('rb') as f:
  if n>18000:f.seek(n-18000)
  text=f.read(18000).decode('utf-8','replace')
alive=True
if pid.exists():
 try:os.kill(int(pid.read_text()),0)
 except ProcessLookupError:alive=False
print(json.dumps(dict(running=not done.exists() and alive,exit=int(done.read_text()) if done.exists() else None,output=text,output_bytes=n,output_path=str(out))))
'''
        result=docker('exec','-e','TBV2_COMMAND='+ident,self.name,'python3','-c',script)
        return json.loads(result['output'])
    def interrupt(self,ident):
        # No command is replayed. Preserve partial files and report interruption.
        docker('exec',self.name,'bash','-c',f'if [ -f /tmp/.tbv2-shell/{ident}.pid ]; then kill -TERM "$(cat /tmp/.tbv2-shell/{ident}.pid)" 2>/dev/null || true; fi',check=False)
    def export_artifacts(self,paths,out):
        out=Path(out);out.mkdir(parents=True,exist_ok=True)
        records=[]
        for src in paths:
            relative=src.strip('/')
            dst=out/relative
            dst.parent.mkdir(parents=True,exist_ok=True)
            if dst.is_symlink() or dst.is_file():dst.unlink()
            elif dst.is_dir():shutil.rmtree(dst)
            # Copy the named directory itself, not its contents into a guessed path.
            r=docker('cp',self.name+':'+src.rstrip('/'),dst,check=False)
            if r['code']==0 and dst.is_symlink():
                dst.unlink();r={'code':1,'output':'Root artifact symlink is not a deliverable'}
            records.append(dict(source=src,local=str(dst),copied=r['code']==0,error=r['output'] if r['code'] else None))
        atomic(out/'manifest.json',records)
        return records
