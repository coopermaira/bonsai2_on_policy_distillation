import json
from controller import RUN
for p in sorted(RUN.glob('*/state.json')):
 s=json.loads(p.read_text());turns=[json.loads(t.read_text()) for t in sorted((p.parent/'turns').glob('*.json'))]
 good=[t['turn'] for t in turns if 'output_path' in t.get('observation',{})]
 errors=[(t['turn'],t['observation']['error']) for t in turns if 'error' in t.get('observation',{})]
 print(p.parent.name,'turn',s['turn'],'tokens',s['generated_tokens'],'tool observations',good,'errors',errors[-4:])
 if turns:
  t=turns[-1];msg=t['assistant'];print('LATEST',t['finish_reason'],'CONTENT',str(msg.get('content'))[:300],'THINK END',str(msg.get('reasoning_content',''))[-600:])
