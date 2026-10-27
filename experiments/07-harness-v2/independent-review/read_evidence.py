import json,sys
from pathlib import Path
root=Path(__file__).parent
ident=sys.argv[1]; mode=sys.argv[2];p=root/ident
if mode=='index':
 for r in json.loads((p/'turns.json').read_text()):
  a=' '.join(json.dumps(r['actions'],ensure_ascii=False).split());o=' '.join(str(r['observation'].get('output',r['observation'])).split());think=' '.join(r['reasoning'].split())
  print(f"T{r['turn']} {r['finish']} {r['tokens']}tok | {a[:120]} | {think[-150:]} | {o[:100]} ... {o[-90:] if len(o)>100 else ''}")
elif mode=='detail':
 ids=set(map(int,sys.argv[3:]));rows=json.loads((p/'turns.json').read_text())
 for r in rows:
  if r['turn'] in ids:
   print('\nTURN',r['turn'],'FINISH',r['finish']);print('THINK:',r['reasoning'][:2500], '\n...END...',r['reasoning'][-2500:] if len(r['reasoning'])>2500 else '');print('ACTION:',json.dumps(r['actions'],ensure_ascii=False)[:7500]);print('OBS:',str(r['observation'])[:5000])
elif mode=='eval':
 v=json.loads((p/'evaluation.json').read_text());print('SCORE',v['score'])
 for t in v['tests']:
  if t['status']!='passed':print(t['name'],t['status'],str(t.get('message',t.get('trace','')))[:1800])
elif mode=='meta':
 v=json.loads((p/'metadata.json').read_text());print({k:v[k] for k in ['turn','generated_tokens','status','compactions','counts']})
