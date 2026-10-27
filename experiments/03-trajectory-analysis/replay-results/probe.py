#!/usr/bin/env python3
"""Bounded, shared-input next-token distribution pilot; executes no model commands."""
import concurrent.futures as cf
import gzip
import hashlib
import json
import math
import os
import signal
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(sys.argv[1])
OUT = BASE / 'probe-results'
OUT.mkdir(exist_ok=True)
URLS = {'fp16':'http://127.0.0.1:8201', 'bonsai':'http://127.0.0.1:8202'}

def http(url, data=None):
    payload = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, payload, {'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=420) as f:
        return json.load(f)

def sha(x):
    return hashlib.sha256(x.encode()).hexdigest()

def write(path, data):
    path.write_text(json.dumps(data, indent=2))

def dist(res):
    rows = res['completion_probabilities'][0]['top_logprobs']
    assert len(rows)>100000, f'Not full vocabulary: {len(rows)}'
    d = {r['id']:r for r in rows}
    assert len(d)==len(rows)
    return d

def compare(a,b):
    assert a.keys()==b.keys(), 'Vocabulary IDs differ'
    assert all(a[i]['bytes']==b[i]['bytes'] for i in a), 'Vocabulary token pieces differ'
    p={i:math.exp(x['logprob']) for i,x in a.items()}
    q={i:math.exp(x['logprob']) for i,x in b.items()}
    sp,sq=sum(p.values()),sum(q.values())
    assert abs(sp-1)<0.002 and abs(sq-1)<0.002, (sp,sq)
    # Normalize only floating point softmax roundoff; full vocabulary is required above.
    p={i:x/sp for i,x in p.items()};q={i:x/sq for i,x in q.items()}
    kl=sum(p[i]*math.log(p[i]/q[i]) for i in p if p[i] and q[i])
    if any(p[i]>0 and q[i]==0 for i in p): kl=None
    js=0.0
    for i in p:
        m=(p[i]+q[i])/2
        if p[i]:js+=.5*p[i]*math.log(p[i]/m)
        if q[i]:js+=.5*q[i]*math.log(q[i]/m)
    ap=sorted(p,key=p.get,reverse=True);bp=sorted(q,key=q.get,reverse=True)
    return dict(vocab_size=len(p),mass_fp16=sp,mass_bonsai=sq,kl_fp16_bonsai_nats=kl,
                js_nats=js,top1_match=ap[0]==bp[0],
                top10_overlap=len(set(ap[:10])&set(bp[:10]))/10,
                top100_overlap=len(set(ap[:100])&set(bp[:100]))/100,
                underflow_fp16=sum(v==0 for v in p.values()),underflow_bonsai=sum(v==0 for v in q.values()),
                fp16_top=[dict(id=i,token=a[i]['token'],p=p[i],q=q[i]) for i in ap[:10]],
                bonsai_top=[dict(id=i,token=b[i]['token'],p=p[i],q=q[i]) for i in bp[:10]])

def main():
    deadline=time.time()+240
    for url in URLS.values():
        while True:
            try:
                http(url+'/health');break
            except Exception:
                if time.time()>deadline:raise
                time.sleep(2)
    for name,url in URLS.items():write(OUT/(name+'-props.json'),http(url+'/props'))
    plan=json.loads((BASE/'probe-plan.json').read_text())
    for item in plan:
        ident=item['id']
        if (OUT/(ident+'.metrics.json')).exists():continue
        request=json.loads(Path(item['request_path']).read_text())
        chat={'messages':request['messages'], 'model':'local'}
        prompts={name:http(url+'/apply-template',chat)['prompt'] for name,url in URLS.items()}
        assert all(isinstance(x,str) for x in prompts.values())
        prompt=prompts['fp16']
        template_same=prompts['fp16']==prompts['bonsai']
        if not template_same: raise RuntimeError('Chat template output differs; do not conflate template and weight differences')
        if item['mode']=='command_boundary':
            response=json.loads(Path(item['response_path']).read_text())
            m=response['choices'][0]['message'];content=m.get('content') or ''
            marker='"keystrokes": "'
            at=content.find(marker)
            if at<0:raise RuntimeError('No literal first command boundary')
            reason=m.get('reasoning_content') or ''
            assert prompt.rstrip().endswith('<think>'), repr(prompt[-150:])
            prompt += reason + '</think>\n\n' + content[:at+len(marker)]
        token_sets={name:http(url+'/tokenize',dict(content=prompt,add_special=True,parse_special=True))['tokens'] for name,url in URLS.items()}
        assert token_sets['fp16']==token_sets['bonsai'], 'Input token IDs differ'
        toks=token_sets['fp16']
        assert len(toks)<196600, 'Context exceeds pilot allocation'
        write(OUT/(ident+'.context.json'),dict(**item,prompt_sha256=sha(prompt),input_tokens=len(toks),
                                             input_token_sha256=sha(json.dumps(toks)),template_equal=template_same))
        payload=dict(prompt=toks,n_predict=1,temperature=0,n_probs=300000,
                     post_sampling_probs=False,return_tokens=True,cache_prompt=False,seed=1)
        print(json.dumps(dict(event='checkpoint_start',id=ident,tokens=len(toks))),flush=True)
        with cf.ThreadPoolExecutor(max_workers=2) as pool:
            fs={name:pool.submit(http,url+'/completion',payload) for name,url in URLS.items()}
            res={name:f.result() for name,f in fs.items()}
        for name,data in res.items():
            with gzip.open(OUT/(ident+'.'+name+'.json.gz'),'wt') as f:json.dump(data,f)
        metrics=dict(**item,input_tokens=len(toks),**compare(dist(res['fp16']),dist(res['bonsai'])))
        write(OUT/(ident+'.metrics.json'),metrics)
        print(json.dumps({k:v for k,v in metrics.items() if not k.endswith('_top') and not k.endswith('_path')}),flush=True)
    write(OUT/'finished.json',dict(finished=True,checkpoints=len(plan),timestamp=time.time()))

if __name__=='__main__':main()
