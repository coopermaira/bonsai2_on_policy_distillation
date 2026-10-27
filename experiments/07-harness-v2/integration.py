"""Run with Docker access in Slurm. Checks real file/env snapshots, no benchmark attempts."""
import json,os,time
from pathlib import Path
from core import DEFAULT,atomic,digest
from runtime import Box,docker
from trial import Trial

ROOT=Path(__file__).resolve().parent
class FakeModel:
    def __init__(self,actions):self.actions=iter(actions)
    def tokens(self,messages):
        text=json.dumps(messages);return text,list(range(len(text)//4+1))
    def count(self,messages):return len(self.tokens(messages)[1])
    def generate(self,messages,cap,seed,sampling):
        action=next(self.actions)
        return dict(usage=dict(prompt_tokens=self.count(messages),completion_tokens=50),choices=[dict(message=dict(role='assistant',content=json.dumps(action)),finish_reason='stop')])

def run(job,images):
    out=ROOT/'validation'/job;out.mkdir(parents=True,exist_ok=True)
    image=images['wal-recovery-ordering']['environment']['id']
    cfg=dict(DEFAULT,total_generated_tokens=1000,output_tokens=200,max_decisions=10)
    ident='snapshot-smoke'
    t=Trial(out,ident,'smoke',FakeModel([dict(command='mkdir -p /app/persist; cd /app/persist; export CHECKPOINT_PROBE=retained; printf once > counter',memory='counter contains once')]),cfg,image,job,'Keep the counter intact.', ['/app/persist/'])
    state=t.run(max_new_turns=1)
    assert state['status']=='paused',state
    t2=Trial(out,ident,'smoke',FakeModel([
        dict(command='test "$PWD" = /app/persist && test "$CHECKPOINT_PROBE" = retained && test "$(cat counter)" = once && printf resumed > result'),
        dict(wait=True),dict(done=True)]),cfg,image,job,'ignored on resume',['/app/persist/'])
    state=t2.run()
    assert state['status']=='completed',state
    assert (out/ident/'artifacts/app/persist/counter').read_text()=='once'
    assert (out/ident/'artifacts/app/persist/result').read_text()=='resumed'
    assert state['memory']=='counter contains once'
    assert state['generated_tokens']==200,state['generated_tokens']
    # Crash during generation reserves usage and is not represented as a failure.
    s=dict(state,phase='requesting',reserved_output=200,turn=4,generated_tokens=200,status='paused')
    atomic(t2.path,s);t2.state=s;t2.recover_interruption()
    assert s['generated_tokens']==400 and not s['usage_valid'] and s['status']=='ready'
    # New file state is unchanged; no shell action was replayed by recovery.
    atomic(out/'integration.json',dict(passed=True,filesystem=True,cwd=True,exported_env=True,
          memory=True,no_command_replay=True,unknown_usage_censored=True))
    return out/'integration.json'

if __name__=='__main__':print(run(os.environ['SLURM_JOB_ID'],json.loads((ROOT/'images.json').read_text())))
