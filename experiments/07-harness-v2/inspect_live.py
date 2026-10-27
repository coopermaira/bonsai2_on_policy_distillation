import json,os
from pathlib import Path
from runtime import docker
from core import atomic
from controller import RUN,JOB
servers=json.loads((RUN/'servers.json').read_text())
rows=[]
for s in servers:
 r=docker('exec',s['name'],'nvidia-smi','--query-gpu=index,uuid,memory.used,memory.total','--format=csv,noheader')
 rows.append(dict(lane=s['lane'],model=s['kind'],allocated_gpu=s['gpu'],gpu=r['output'].strip()))
atomic(RUN/'gpu-validation.json',rows)
print(json.dumps(rows,indent=2))
for p in sorted(RUN.glob('*/turns/*.json')):
 row=json.loads(p.read_text())
 if row['turn']<=3:
  print(p.parent.parent.name,row['turn'],str(row['assistant'].get('content'))[:180],str(row.get('observation'))[:250])
# Give the owner normal control of the output directory, including pilot files.
for d in [RUN.parent,RUN]:os.chown(d,1014,1014)
