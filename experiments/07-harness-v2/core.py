"""Common, model-independent execution policy. No evaluator material enters this module."""
import hashlib
import json
import os
import re
from pathlib import Path

SYSTEM = '''You are solving a terminal task in an isolated Linux container.
Call the act tool with an object containing exactly one action. Optional analysis
and plan strings may accompany the action:
{"command":"shell script"} executes a noninteractive bash script;
{"wait":true} polls a running command;
{"recall":{"turn":1,"offset":0,"limit":12000}} retrieves an archived turn;
{"done":true} declares your work complete.
You may include "memory": "..." to REPLACE your durable notebook (maximum 8192
characters). Keep requirements, verified facts, rejected hypotheses, changed files,
test results, and next steps there; distinguish facts from guesses. The notebook
survives context compaction. All prior turns are archived and retrievable by turn
number; compaction does not reset the filesystem. Large outputs can be read from
the command-output path reported by the tool. A command may remain running; poll
it with wait before starting another command. There is no task wall-clock deadline.
Use the remaining generated-token and decision budgets reported by the harness.
Commands run in fresh bash processes with the last working directory and exported
environment restored. Interactive terminal input is not supported. Start servers
in the background if needed. A resumed allocation preserves filesystem changes,
but processes must be restarted; the harness will tell you when this occurs.
Do not look for benchmark solutions or hidden tests. Work from the task and visible
environment. Only claim completion after checking the requested behavior.'''

DEFAULT = dict(context_tokens=65536, output_tokens=16384, output_reserve=512,
               total_generated_tokens=262144, max_decisions=512, memory_chars=8192,
               observation_chars=18000, seed=20261004,
               sampling=dict(temperature=0.6, top_p=0.95, top_k=20, min_p=0.0))

class InfrastructureError(RuntimeError): pass

def atomic(path, obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    with temp.open('w') as f:
        json.dump(obj,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
    fd=os.open(path.parent,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def task_instruction(text):
    # Remove ONLY the benchmark's agent deadline sentence. Preserve task contracts.
    return re.sub(r'You have \d+(?:\.\d+)? seconds to complete this task\.\s*','',text).strip()

def parse_action(content):
    text=content.strip()
    # Accept the native envelope only around one complete JSON action. This
    # changes serialization, never repairs JSON or executes a clipped prefix.
    if text.startswith('<tool_call>'):
        match=re.fullmatch(r'<tool_call>\s*(.*?)\s*(?:</(?:parameter|function|package)>\s*)*</tool_call>',text,re.S)
        if not match:raise ValueError('Incomplete native tool envelope')
        text=match.group(1).strip()
    if text.startswith('```'):
        text=re.sub(r'^```(?:json)?\s*','',text)
        text=re.sub(r'\s*```$','',text)
    obj=json.loads(text)
    if not isinstance(obj,dict): raise ValueError('Response must be a JSON object')
    kinds=[k for k in ('command','wait','recall','done') if k in obj]
    if len(kinds)!=1:raise ValueError('Exactly one action is required')
    if 'memory' in obj and (not isinstance(obj['memory'],str) or len(obj['memory'])>8192):
        raise ValueError('memory must be a string of at most 8192 characters')
    kind=kinds[0]
    if kind=='command' and (not isinstance(obj[kind],str) or not obj[kind].strip() or len(obj[kind])>60000):
        raise ValueError('command must be a nonempty shell script of at most 60000 characters')
    if kind in ('wait','done') and obj[kind] is not True:raise ValueError(kind+' must be true')
    if kind=='recall':
        r=obj[kind]
        if not isinstance(r,dict) or type(r.get('turn')) is not int or r['turn']<1:raise ValueError('Invalid recall turn')
        for k,default in [('offset',0),('limit',12000)]:
            if type(r.get(k,default)) is not int:raise ValueError('Recall bounds must be integers')
        if r.get('offset',0)<0 or not 1<=r.get('limit',12000)<=18000:raise ValueError('Invalid recall bounds')
    return obj

def recall(archive, request):
    path=Path(archive)/f"{request['turn']:04}.json"
    if not path.exists():return {'error':'No such completed/recorded turn'}
    # Agent-visible fields only. Never expose paths to evaluator bundles or future turns.
    row=json.loads(path.read_text())
    visible={k:row[k] for k in ('turn','assistant','observation') if k in row}
    text=json.dumps(visible,ensure_ascii=False,indent=2)
    offset=request.get('offset',0);limit=request.get('limit',12000)
    return dict(turn=request['turn'],offset=offset,total_chars=len(text),text=text[offset:offset+limit],
                next_offset=offset+limit if offset+limit<len(text) else None)

def budget_message(state,config):
    return ('Remaining generated-token budget (includes reasoning): '
            f"{max(0,config['total_generated_tokens']-state['generated_tokens'])}; "
            f"remaining decisions: {max(0,config['max_decisions']-state['turn'])}. "
            f"Archived turns: 1..{state['turn']}. "
            + ('A command is running; use wait. ' if state.get('pending_command') else ''))

def compact(messages,instruction,memory,turn,count,limit):
    """Mechanical compaction, never an LLM-generated assertion of task facts.

    Keep the immutable task, complete notebook, latest observation, and as much
    recent conversation as fits. Full omitted history remains in recall storage.
    """
    header=f'''CONTEXT COMPACTED after turn {turn}. Filesystem unchanged.
The full history remains available through recall(turn, offset, limit).
The following notebook is model-authored and may contain mistaken beliefs:
<notebook>\n{memory or '(empty)'}\n</notebook>
Original task, preserved verbatim after removal of its agent-deadline sentence:
<task>\n{instruction}\n</task>'''
    prefix=[{'role':'system','content':SYSTEM},{'role':'user','content':header}]
    # Preserve a complete recent assistant/observation suffix. Do not silently
    # discard the latest tool result or notebook to force a request through.
    suffix=[m for m in messages[2:] if m['role'] in ('assistant','user','tool')]
    for keep in range(min(12,len(suffix)),0,-1):
        tail=suffix[-keep:]
        if tail and tail[0]['role']=='tool':continue
        candidate=prefix+tail
        if count(candidate)<=limit:return candidate
    if not suffix and count(prefix)<=limit:return prefix
    raise InfrastructureError('Immutable task/notebook/latest observation cannot fit reserved context')

def prepare_messages(state,config,count):
    messages=state['messages']+[{'role':'user','content':budget_message(state,config)}]
    limit=config['context_tokens']-min(config['output_tokens'],config['total_generated_tokens']-state['generated_tokens'])-config['output_reserve']
    before=count(messages)
    if before<=limit:return messages,None
    compacted=compact(state['messages'],state['instruction'],state.get('memory',''),state['turn'],
                      lambda ms:count(ms+[messages[-1]]),limit)
    result=compacted+[messages[-1]]
    after=count(result)
    assert after<=limit
    return result,dict(before_tokens=before,after_tokens=after,turn=state['turn'],
                       type='mechanical_notebook_and_retrievable_history')

def score_groups(tests,groups,exclude=()):
    """Prespecified requirement-group means, never raw test-count weighting.
    Missing/error/timeout checks remain unknown and produce score bounds.
    """
    rows=[]
    for group,patterns in groups.items():
        selected=[t for t in tests if any((t['name'].split('::')[-1].split('[')[0]==p[1:]) if p.startswith('=') else p in t['name'] for p in patterns) and not any(e in t['name'] for e in exclude)]
        known=[];unknown=0
        for t in selected:
            detail=str(t.get('message',''))+' '+str(t.get('trace',''))
            if any(x in detail.lower() for x in ('timeoutexpired','timeouterror','timed out','verifier_incomplete','exceeded time')):
                unknown+=1
            elif t['status']=='passed':known.append(1)
            elif t['status']=='failed':known.append(0)
            else:unknown+=1
        total=len(known)+unknown
        rows.append(dict(group=group,checks=total,
                         lower=sum(known)/total if total else 0,
                         upper=(sum(known)+unknown)/total if total else 1,
                         unknown=unknown if total else 1))
    return dict(groups=rows,lower=100*sum(x['lower'] for x in rows)/len(rows),
                upper=100*sum(x['upper'] for x in rows)/len(rows))
