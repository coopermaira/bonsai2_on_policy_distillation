#!/usr/bin/env python3
"""Join finalized semantic labels to model IDs and estimate local-policy rates."""
import csv
import json
import math
from collections import Counter
from pathlib import Path
from scipy.stats import fisher_exact

ROOT=Path(__file__).resolve().parent
def wilson(x,n):
    z=1.959963984540054;p=x/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den
    rad=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,center-rad),min(1,center+rad)]
def difference(b,nb,f,nf):
    pb,pf=b/nb,f/nf;bl,bu=wilson(b,nb);fl,fu=wilson(f,nf)
    return dict(estimate=pb-pf,ci95=[pb-pf-math.sqrt((pb-bl)**2+(fu-pf)**2),
                                    pb-pf+math.sqrt((bu-pb)**2+(pf-fl)**2)])
def main():
    labels=list(csv.DictReader((ROOT/'labels.csv').open()))
    key=json.loads((ROOT/'blinding-key.json').read_text())
    blind={r['blind_id']:r for r in map(json.loads,(ROOT/'blind.jsonl').read_text().splitlines())}
    assert len({r['blind_id'] for r in labels})==len(labels)==240
    assert set(r['blind_id'] for r in labels)==set(key)
    allowed={'image_commitment','diagnose_representation','vector_pivot','render_agnostic','other','unusable'}
    joined=[]
    for row in labels:
        assert row['label'] in allowed
        ident=row['blind_id'];r=blind[ident];k=key[ident]
        if row['label']=='vector_pivot':assert row['premise_rejected']=='true'
        joined.append(dict(**row,**k,state=r['state'],finish=r['finish'],strict_json_valid=r['strict_json_valid']))
    summary=[]
    for state in ['selection','recovery_api','recovery_evidence']:
        success={'image_commitment'} if state=='selection' else {'vector_pivot'}
        sub={m:[r for r in joined if r['model']==m and r['state']==state] for m in ['bonsai','fp16']}
        row=dict(state=state,endpoint='image_commitment' if state=='selection' else 'explicit_recovery')
        counts={}
        for m,rs in sub.items():
            assert len(rs)==40
            x=sum(r['label'] in success for r in rs);counts[m]=x
            u=sum(r['label']=='unusable' for r in rs);valid=[r for r in rs if r['label']!='unusable']
            notcapped=[r for r in rs if r['finish']!='length']
            row[m]=dict(n=len(rs),events=x,rate=x/len(rs),ci95=wilson(x,len(rs)),
                categories=dict(Counter(r['label'] for r in rs)),unusable=u,
                endpoint_bounds=[x/len(rs),(x+u)/len(rs)],
                valid_only_rate=sum(r['label'] in success for r in valid)/len(valid) if valid else None,
                capped=sum(r['finish']=='length' for r in rs),
                uncapped_rate=sum(r['label'] in success for r in notcapped)/len(notcapped) if notcapped else None,
                broad_escape=sum(r['label'] in {'diagnose_representation','vector_pivot','render_agnostic'} for r in rs))
        row['difference_bonsai_minus_fp16']=difference(counts['bonsai'],40,counts['fp16'],40)
        row['broad_escape_difference_bonsai_minus_fp16']=difference(row['bonsai']['broad_escape'],40,row['fp16']['broad_escape'],40)
        for m in ['bonsai','fp16']:
            row[m]['broad_escape_ci95']=wilson(row[m]['broad_escape'],40)
        row['fisher_p']=fisher_exact([[counts['bonsai'],40-counts['bonsai']],[counts['fp16'],40-counts['fp16']]]).pvalue
        summary.append(row)
    previous=0
    for i,row in enumerate(sorted(summary,key=lambda r:r['fisher_p'])):
        previous=max(previous,min(1,(3-i)*row['fisher_p']));row['holm_p']=previous
    (ROOT/'statistics.json').write_text(json.dumps(summary,indent=2))
    # All six malformed outputs have model-hidden semantic judgments recorded
    # in ANNOTATION_NOTES.md. This sensitivity accepts their recoverable envelope.
    interpreted={'accfe05f':'diagnose_representation','9e44bb8b':'image_commitment',
                 'a21b448d':'image_commitment','afd111a5':'image_commitment',
                 'bfe7f6a6':'image_commitment','c0418259':'vector_pivot'}
    semantic=[]
    for state in ['selection','recovery_api','recovery_evidence']:
        row={'state':state}
        for model in ['bonsai','fp16']:
            rs=[r for r in joined if r['state']==state and r['model']==model]
            categories=Counter(interpreted.get(r['blind_id'],r['label']) for r in rs)
            row[model]=dict(n=len(rs),categories=dict(categories),
                image_commitment=categories['image_commitment'],explicit_correction=categories['vector_pivot'],
                broad_escape=sum(categories[k] for k in ['diagnose_representation','vector_pivot','render_agnostic']))
        row['broad_escape_difference_bonsai_minus_fp16']=difference(row['bonsai']['broad_escape'],40,row['fp16']['broad_escape'],40)
        semantic.append(row)
    (ROOT/'protocol-semantic-sensitivity.json').write_text(json.dumps(semantic,indent=2))
    with (ROOT/'labeled-samples.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(joined[0]));w.writeheader();w.writerows(joined)
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
