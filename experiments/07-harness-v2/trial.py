import copy, json, os, threading, traceback
from pathlib import Path
from core import DEFAULT, SYSTEM, InfrastructureError, atomic, digest, parse_action, prepare_messages, recall, task_instruction
from runtime import Box, action_text

STOP=threading.Event()
TERMINAL={'completed','budget_exhausted'}

class Trial:
    def __init__(self,root,ident,task,model,config,image,job,instruction,artifacts):
        self.root=Path(root)/ident;self.root.mkdir(parents=True,exist_ok=True)
        self.archive=self.root/'turns';self.archive.mkdir(exist_ok=True)
        self.path=self.root/'state.json';self.model=model;self.config=config
        self.ident=ident;self.artifacts=artifacts
        self.box=Box('tbv2-'+job+'-'+ident,job,self.root)
        if self.path.exists():
            self.state=json.loads(self.path.read_text())
            if self.state['config_hash']!=digest(config):raise InfrastructureError('Resume config differs')
        else:
            instruction=task_instruction(instruction)
            self.state=dict(schema=1,id=ident,task=task,config_hash=digest(config),turn=0,generated_tokens=0,
                instruction=instruction,memory='',status='ready',phase='idle',checkpoint_image=image,
                pending_command=None,compactions=[],usage_valid=True,interruptions=[],
                messages=[dict(role='system',content=SYSTEM),dict(role='user',content=instruction)])
            self.save()
    def save(self):atomic(self.path,self.state)
    def checkpoint(self):
        image=self.box.snapshot('cmaira/tbv2-checkpoint:'+digest(str(self.root))[:12]+'-'+self.ident)
        self.state['checkpoint_image']=image
        self.save()
    def recover_interruption(self):
        s=self.state
        if s['phase']=='requesting':
            # A response may have been lost. Do not pretend to know its usage or
            # silently retry the same request. Reserve its entire allowed budget.
            s['generated_tokens']+=s.pop('reserved_output',0)
            s['turn']+=1;s['usage_valid']=False
            s['interruptions'].append('Model request interrupted; actual usage unknown, full cap reserved.')
        if s.get('pending_command') or s['phase'] in ('executing','response_saved'):
            s['interruptions'].append('Interrupted action not replayed. Files restored from last recorded checkpoint; inspect before continuing.')
        s['pending_command']=None;s['phase']='idle'
        s['messages'].append(dict(role='user',content='Allocation resumed. Filesystem restored from recorded checkpoint; previous processes are no longer running. No shell command has been automatically replayed. Inspect state and restart any required background services. '+str(s['interruptions'][-1:])))
        s['status']='ready';self.save()
    def run(self,max_new_turns=None):
        s=self.state;c=self.config
        if s['status'] in TERMINAL:
            if not (self.root/'artifacts/manifest.json').exists():
                self.box.start(s['checkpoint_image'])
                try:self.box.export_artifacts(self.artifacts,self.root/'artifacts')
                finally:self.box.remove()
            return s
        is_resume=s['turn']>0 or s['phase']!='idle'
        self.box.start(s['checkpoint_image'])
        try:
            if is_resume:self.recover_interruption()
            started_turn=s['turn']
            while not STOP.is_set():
                if s['generated_tokens']>=c['total_generated_tokens'] or s['turn']>=c['max_decisions']:
                    s['status']='budget_exhausted';break
                if max_new_turns is not None and s['turn']-started_turn>=max_new_turns:
                    s['status']='paused';break
                messages,event=prepare_messages(s,c,self.model.count)
                if event:s['compactions'].append(event);s['messages']=messages[:-1]
                cap=min(c['output_tokens'],c['total_generated_tokens']-s['generated_tokens'])
                n=s['turn']+1
                request=dict(messages=messages,cap=cap,seed=c['seed']+n,sampling=c['sampling'])
                prompt,ids=self.model.tokens(messages)
                atomic(self.root/f'request-{n:04}.json',dict(**request,prompt=prompt,input_tokens=ids))
                s['phase']='requesting';s['reserved_output']=cap;s['status']='running';self.save()
                response=self.model.generate(messages,cap,request['seed'],c['sampling'])
                atomic(self.root/f'response-{n:04}.json',response)
                usage=response.get('usage',{})
                used=usage.get('completion_tokens');actual_prompt=usage.get('prompt_tokens')
                if type(used) is not int or not 0<=used<=cap:raise InfrastructureError('Missing/invalid completion-token accounting')
                if actual_prompt!=len(ids):raise InfrastructureError(f'Server/template token count differs: {actual_prompt} vs {len(ids)}')
                msg=response['choices'][0]['message'];finish=response['choices'][0].get('finish_reason')
                content=msg.get('content') or ''
                row=dict(turn=n,assistant=msg,usage=usage,finish_reason=finish,request_hash=digest(request))
                atomic(self.archive/f'{n:04}.json',row)
                s['generated_tokens']+=used;s['turn']=n;s.pop('reserved_output',None)
                s['phase']='response_saved';s['messages']=messages+[msg]
                self.save()
                # A clipped action is never executed, even if a substring is JSON.
                try:
                    if finish=='length':raise ValueError('Response hit the per-response token cap; no action executed. Use a shorter response.')
                    action=parse_action(action_text(msg))
                except (ValueError,TypeError) as exc:
                    observation=dict(error=str(exc),executed=False)
                else:
                    if 'memory' in action:s['memory']=action['memory']
                    if 'recall' in action:
                        if action['recall']['turn']>=n:observation={'error':'Recall only earlier turns'}
                        else:observation=recall(self.archive,action['recall'])
                    elif 'command' in action:
                        if s['pending_command']:observation={'error':'A command is still running; use wait','executed':False}
                        else:
                            ident=f'c{n:04}'
                            s['pending_command']=ident;s['phase']='executing';self.save()
                            self.box.launch(action['command'],ident)
                            observation=self.box.poll(ident)
                            if not observation['running']:s['pending_command']=None
                    elif 'wait' in action:
                        if s['pending_command']:
                            observation=self.box.poll(s['pending_command'],delay=5)
                            if not observation['running']:s['pending_command']=None
                        else:observation={'running':False,'message':'No command is running'}
                    else:
                        if s['pending_command']:observation={'error':'Cannot complete while a command runs; use wait'}
                        else:s['status']='completed';observation={'declared_complete':True}
                row['observation']=observation;atomic(self.archive/f'{n:04}.json',row)
                calls=msg.get('tool_calls') or []
                if calls:
                    for call in calls:s['messages'].append(dict(role='tool',tool_call_id=call['id'],content=json.dumps(observation,ensure_ascii=False)))
                else:s['messages'].append(dict(role='user',content=json.dumps(observation,ensure_ascii=False)))
                s['phase']='idle'
                # A paired filesystem/state commit is published only after the
                # action journal is durable. Interrupted side effects are never replayed.
                self.checkpoint()
                if s['status']=='completed':break
            if STOP.is_set():s['status']='paused'
            if s.get('pending_command') and s['status'] in TERMINAL:
                self.box.interrupt(s['pending_command'])
                s['interruptions'].append('Running command stopped at the prespecified token/action budget boundary.')
                s['pending_command']=None
            self.checkpoint()
            if s['status'] in TERMINAL:self.box.export_artifacts(self.artifacts,self.root/'artifacts')
        except Exception as exc:
            s['status']='infrastructure_incomplete'
            atomic(self.root/'error.json',dict(error=repr(exc),traceback=traceback.format_exc()))
            # Preserve whatever filesystem exists, without converting this to a
            # zero reward. The next allocation may resume from it.
            try:self.checkpoint()
            except Exception:self.save()
        finally:self.box.remove()
        return s
