import json,os
from pathlib import Path
from core import DEFAULT,SYSTEM,prepare_messages,atomic
from runtime import Model
root=Path(__file__).resolve().parent/'runs/oct04-eight-new'
results=[]
for lane in [0,3]:
 m=Model('http://127.0.0.1:'+str(18900+lane))
 instruction='Protocol check only. Return {"done":true}. Preserve marker IMMUTABLE_817.'
 state=dict(messages=[dict(role='system',content=SYSTEM),dict(role='user',content=instruction),dict(role='assistant',content='Earlier material. '*55000),dict(role='user',content='Latest observation: RETAIN_913.')],instruction=instruction,memory='Verified note NOTE_521.',turn=2,generated_tokens=0)
 messages,event=prepare_messages(state,DEFAULT,m.count)
 assert event and 'IMMUTABLE_817' in str(messages) and 'RETAIN_913' in str(messages) and 'NOTE_521' in str(messages)
 response=m.generate(messages,1024,1,DEFAULT['sampling'])
 assert response['usage']['prompt_tokens']==m.count(messages)
 results.append(dict(lane=lane,event=event,response=response))
atomic(root/'live-context-check.json',dict(passed=True,checks=results))
print('LIVE CONTEXT CHECK PASSED',flush=True)
