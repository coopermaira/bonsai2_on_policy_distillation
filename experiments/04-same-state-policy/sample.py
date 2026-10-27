#!/usr/bin/env python3
import concurrent.futures as cf
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT=Path(sys.argv[1]); OUT=ROOT/'outputs'; OUT.mkdir(exist_ok=True)
URLS={'fp16':'http://127.0.0.1:8211','bonsai':'http://127.0.0.1:8212'}
def save(p,obj):
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(obj,indent=2));tmp.replace(p)
def http(url,obj=None):
    req=urllib.request.Request(url,None if obj is None else json.dumps(obj).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=900) as f:return json.load(f)
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def sample(model,state,messages,i,seed):
    ident=f'{state}-{model}-{i:03d}';p=OUT/(ident+'.json')
    if p.exists():return
    body=dict(model='local',messages=messages,temperature=1.0,top_k=20,top_p=.95,min_p=.05,
              repeat_penalty=1.0,presence_penalty=0.0,frequency_penalty=0.0,
              seed=seed,max_tokens=8192,cache_prompt=True)
    record=dict(id=ident,state=state,model=model,sample=i,seed=seed,
                request_parameters={k:v for k,v in body.items() if k!='messages'},
                messages_sha256=sha(json.dumps(messages)),started=time.time())
    try:
        response=http(URLS[model]+'/v1/chat/completions',body)
        record.update(response=response,elapsed=time.time()-record['started'])
        save(p,record)
        print(json.dumps(dict(id=ident,finish=response['choices'][0]['finish_reason'],usage=response.get('usage'))),flush=True)
    except Exception as e:
        record.update(error=repr(e),elapsed=time.time()-record['started']);save(OUT/(ident+'.error.json'),record)
        print(json.dumps(dict(id=ident,error=repr(e))),flush=True)
        raise
def main():
    deadline=time.time()+300
    for model,url in URLS.items():
        while True:
            try:http(url+'/health');break
            except Exception:
                if time.time()>deadline:raise
                time.sleep(2)
        save(ROOT/(model+'-props.json'),http(url+'/props'))
    plan=json.loads((ROOT/'plan.json').read_text())
    for si,item in enumerate(plan):
        state=item['state'];messages=json.loads((ROOT/(state+'.messages.json')).read_text())
        prompts={m:http(url+'/apply-template',dict(model='local',messages=messages))['prompt'] for m,url in URLS.items()}
        assert prompts['fp16']==prompts['bonsai'],'template mismatch'
        toks={m:http(url+'/tokenize',dict(content=prompts[m],add_special=True,parse_special=True))['tokens'] for m,url in URLS.items()}
        assert toks['fp16']==toks['bonsai'],'token mismatch'
        assert len(toks['fp16'])+8192<32768,'context overflow'
        save(ROOT/(state+'.context.json'),dict(input_tokens=len(toks['fp16']),prompt_sha256=sha(prompts['fp16']),
             input_token_sha256=sha(json.dumps(toks['fp16'])),template_equal=True,input_tokens_equal=True))
        # Per-model pools bound active requests to server slots; states stay sequential.
        with cf.ThreadPoolExecutor(max_workers=4) as fp,cf.ThreadPoolExecutor(max_workers=4) as bs:
            futures=[]
            for mi,(model,pool) in enumerate([('fp16',fp),('bonsai',bs)]):
                for i in range(item['samples_per_model']):
                    seed=20260929+si*1000+mi*100+i
                    futures.append(pool.submit(sample,model,state,messages,i,seed))
            for f in cf.as_completed(futures):f.result()
    save(ROOT/'finished.json',dict(finished=True,samples=240,timestamp=time.time()))
if __name__=='__main__':main()
