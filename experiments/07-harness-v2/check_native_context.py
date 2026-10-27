import concurrent.futures,json
from core import DEFAULT,SYSTEM,prepare_messages,atomic,parse_action
from runtime import Model,action_text
from controller import RUN
servers=json.loads((RUN/'servers.json').read_text())
def check(lane):
 m=Model('http://127.0.0.1:'+str(servers[lane]['port']))
 instruction='Protocol check only. Call act with done=true now. Preserve marker IMMUTABLE_817.'
 messages=[dict(role='system',content=SYSTEM),dict(role='user',content=instruction)]
 for i in range(40):
  messages.extend([dict(role='assistant',content='Earlier material. '*1800,tool_calls=[dict(id='c'+str(i),type='function',function=dict(name='act',arguments='{"command":"echo inspection"}'))]),dict(role='tool',tool_call_id='c'+str(i),content='Recorded observation.')])
 messages.extend([dict(role='assistant',content='',tool_calls=[dict(id='last',type='function',function=dict(name='act',arguments='{"command":"echo final"}'))]),dict(role='tool',tool_call_id='last',content='Latest observation RETAIN_913. Protocol check complete; call act with done=true.')])
 state=dict(messages=messages,instruction=instruction,memory='Verified note NOTE_521.',turn=41,generated_tokens=0)
 compacted,event=prepare_messages(state,DEFAULT,m.count)
 assert event and all(x in str(compacted) for x in ['IMMUTABLE_817','RETAIN_913','NOTE_521'])
 assert compacted[-2]['role']=='tool' and compacted[-3]['tool_calls'][0]['id']==compacted[-2]['tool_call_id']
 response=m.generate(compacted,1024,1,DEFAULT['sampling'])
 assert response['usage']['prompt_tokens']==m.count(compacted)
 assert parse_action(action_text(response['choices'][0]['message'])).get('done') is True
 return dict(lane=lane,event=event,response=response)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:results=list(ex.map(check,[0,3]))
atomic(RUN/'native-live-context-check.json',dict(passed=True,checks=results))
print('NATIVE LIVE CONTEXT CHECK PASSED')
