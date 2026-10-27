#!/usr/bin/env python3
"""Create stable shuffled IDs and model-hidden semantic review material."""
import hashlib
import json
import secrets
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from extract import proposal
saltfile=ROOT/'blinding-salt.txt'
if not saltfile.exists():saltfile.write_text(secrets.token_hex(32))
salt=saltfile.read_text()
rows=[];key={}
for p in sorted((ROOT/'outputs').glob('*.json')):
    if p.name.endswith('.error.json'):continue
    d=json.loads(p.read_text());ident=hashlib.sha256((salt+d['id']).encode()).hexdigest()[:8]
    choice=d['response']['choices'][0];m=choice['message'];content=m.get('content') or ''
    obj=proposal(content)
    rows.append(dict(blind_id=ident,state=d['state'],finish=choice['finish_reason'],
        analysis=(obj or {}).get('analysis'),plan=(obj or {}).get('plan'),commands=(obj or {}).get('commands'),
        content=content,reasoning=m.get('reasoning_content') or '',strict_json_valid=False))
    try:
        strict=json.loads(content)
        rows[-1]['strict_json_valid']=isinstance(strict,dict) and isinstance(strict.get('commands'),list)
    except ValueError:pass
    key[ident]=dict(id=d['id'],model=d['model'],sample=d['sample'],seed=d['seed'],path=str(p))
rows.sort(key=lambda r:r['blind_id'])
(ROOT/'blind.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
(ROOT/'blinding-key.json').write_text(json.dumps(key,indent=2))
print(f'{len(rows)} blinded samples prepared')
