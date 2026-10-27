import hashlib,json,re
from pathlib import Path
BASE=Path('/mnt/data/private/cmaira/bonsai_perf')
ROOT=BASE/'retrospective-20261003'
ROOT.mkdir(exist_ok=True)
manifest=[]
for path in sorted((BASE/'harbor_jobs').glob('comparison-20260929-065104-*/*/agent/trajectory.json')):
    d=json.loads(path.read_text());task=path.parents[1].name.split('__')[0]
    model='bonsai' if 'bonsai' in path.parents[2].name else 'qwen'
    ident=task+'-'+model
    out=ROOT/'review'/ident;out.mkdir(parents=True,exist_ok=True)
    lines=[]
    turns=[]
    for s in d['steps']:
        if s.get('source')!='agent':continue
        n=len(turns)+1
        message=s.get('message') or ''
        calls=s.get('tool_calls') or []
        obs='\n'.join(r.get('content','') for r in (s.get('observation') or {}).get('results',[]))
        commands='\n'.join(str(c.get('arguments',{}).get('keystrokes','')) for c in calls)
        full=f"RESPONSE {n}, trajectory step {s['step_id']}\n{message}\n\nCOMMANDS\n{commands}\n\nOBSERVATION\n{obs}\n\nRECORDED REASONING\n{s.get('reasoning_content') or ''}\n"
        (out/f'{n:03}.txt').write_text(full)
        lines.append(f"\nRESPONSE {n} STEP {s['step_id']}\n{message}\nCOMMAND STARTS: "+' | '.join(str(c.get('arguments',{}).get('keystrokes','')).splitlines()[0][:140] if str(c.get('arguments',{}).get('keystrokes','')).splitlines() else '<empty>' for c in calls))
        turns.append({'response':n,'step':s['step_id'],'file':f'{n:03}.txt','message_chars':len(message),'command_chars':len(commands),'observation_chars':len(obs)})
    (out/'digest.txt').write_text('\n'.join(lines))
    (out/'index.json').write_text(json.dumps(turns,indent=2))
    manifest.append({'id':ident,'trajectory':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'agent_steps':len(turns)})
(ROOT/'review-manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
