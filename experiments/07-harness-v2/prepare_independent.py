import json, collections, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUN=ROOT/'runs/oct04-eight-new-tools'
OUT=ROOT/'independent-review-input';OUT.mkdir(exist_ok=True)
manifest={}
for folder in sorted(RUN.glob('*/turns')):
 ident=folder.parent.name
 dest=OUT/ident;dest.mkdir(exist_ok=True)
 state=json.loads((folder.parent/'state.json').read_text())
 rows=[];index=[];counts=collections.Counter()
 for path in sorted(folder.glob('*.json')):
  r=json.loads(path.read_text());msg=r['assistant'];obs=r.get('observation',{});args=[]
  for call in msg.get('tool_calls',[]):
   raw=call.get('function',{}).get('arguments','')
   try:args.append(json.loads(raw) if isinstance(raw,str) else raw)
   except Exception:args.append({'malformed_arguments':raw})
  if not args:
   try:args=[json.loads(msg.get('content',''))]
   except Exception:args=[{'text':msg.get('content','')}]
  text=json.dumps(args,ensure_ascii=False)
  reasoning=msg.get('reasoning_content','') or ''
  counts[r['finish_reason']]+=1
  if 'error' in obs:counts['feedback_error']+=1
  if 'command' in text:counts['command_turns']+=1
  row=dict(turn=r['turn'],finish=r['finish_reason'],tokens=r['usage']['completion_tokens'],reasoning=reasoning,actions=args,observation=obs)
  rows.append(row)
  action=' '.join(text.split())
  observation=' '.join(str(obs.get('output',obs)).split())
  index.append(f"T{r['turn']:03} [{r['finish_reason']}; {r['usage']['completion_tokens']} tok; exit={obs.get('exit')}]: {action[:190]}\n  THINK: {' '.join(reasoning.split())[-230:]}\n  OBS: {observation[:180]}{' ... '+observation[-120:] if len(observation)>300 else ''}\n")
 (dest/'turns.json').write_text(json.dumps(rows,indent=2))
 (dest/'index.txt').write_text('\n'.join(index))
 meta={k:v for k,v in state.items() if k!='messages'};meta['counts']=dict(counts)
 (dest/'metadata.json').write_text(json.dumps(meta,indent=2))
 for name in ['error.json','verification/evaluation.json']:
  p=folder.parent/name
  if p.exists():shutil.copy2(p,dest/Path(name).name)
 manifest[ident]=dict(turns=len(rows),status=state['status'],generated_tokens=state['generated_tokens'],compactions=len(state['compactions']),counts=dict(counts))
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
shutil.make_archive(str(ROOT/'independent-review-input'),'gztar',OUT)
print(json.dumps(manifest,indent=2))
