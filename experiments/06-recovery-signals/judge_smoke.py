import json
import time
import signals
from study import WORK, http, save

signals.OUT = WORK / 'signal-smoke'
signals.OUT.mkdir(exist_ok=True)
signals.URLS['fp16'] = 'http://127.0.0.1:8240'
for _ in range(150):
    try:
        http(signals.URLS['fp16'] + '/health', timeout=3)
        break
    except Exception:
        time.sleep(2)
else:
    raise RuntimeError('Judge server startup failed')
record = json.loads((WORK/'rollouts/music_evidence-bonsai-02.json').read_text())
turn = record['turns'][0]
for mode in ['full','commands']:
    signals.judge('smoke-original', record['initial_messages'], turn['action'], mode)
    path = signals.OUT/f'smoke-original.judge-{mode}.json'
    result=json.loads(path.read_text())
    print(json.dumps({'mode':mode,'score':result.get('score'),'error':result.get('error')}),flush=True)
    assert result.get('score'), result
# Negative control tests whether the judge can reject a plainly unsupported action.
bad={'analysis':'The PDF must be an image because the resource names contain Image.','plan':'Extract the embedded images.',
     'commands':[{'keystrokes':"python3 -c \"import pypdf; print(pypdf.PdfReader('/app/Harmony.pdf').pages[0].get_resources())\"\n",'duration':1}]}
signals.judge('smoke-known-api-error',record['initial_messages'],bad,'full')
result=json.loads((signals.OUT/'smoke-known-api-error.judge-full.json').read_text())
print(json.dumps({'negative_control':result.get('score'),'error':result.get('error')}),flush=True)
assert result.get('score'),result
save(WORK/'judge-smoke-finished.json',{'finished':True})
