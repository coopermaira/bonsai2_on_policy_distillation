import json,os
from pathlib import Path
from verify import ROOT,preflight
for task in ['html-js-filter','rs-archive-clone']:
 for kind in ['baseline','reference']:
  path=ROOT/'preflight'/task/kind/'verification'
  path.rename(path.with_name('verification-before-fix'))
(ROOT/'preflight.json').rename(ROOT/'preflight-before-fix.json')
results=preflight(json.loads((ROOT/'images.json').read_text()),os.environ['SLURM_JOB_ID'])
for task,pair in results.items():
 print(task,{k:(v['status'],v['score']['lower'],v['score']['upper']) for k,v in pair.items()},flush=True)
 assert pair['reference']['score']['lower']==100,task
