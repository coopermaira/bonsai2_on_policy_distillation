#!/usr/bin/env python3
"""model_compare.py BINDIR ROUNDS REPS TESTARGS -- label=/path/to/model.gguf ..."""
import sys,subprocess,os,csv,io,statistics as st
bindir=sys.argv[1]; rounds=int(sys.argv[2]); reps=sys.argv[3]; sep=sys.argv.index('--')
targs=sys.argv[4:sep]; variants=[]
for v in sys.argv[sep+1:]:
    lab,path=v.split('=',1); variants.append((lab,path))
res={l:{} for l,_ in variants}
meta={}
def gpu():
    return subprocess.run(['nvidia-smi','--query-gpu=clocks.sm,clocks.mem,power.draw,temperature.gpu','--format=csv,noheader'],capture_output=True,text=True).stdout.strip()
print('gpu before:',gpu(),flush=True)
for r in range(rounds):
    for lab,path in variants:
        e=dict(os.environ,LD_LIBRARY_PATH=bindir)
        out=subprocess.run([bindir+'/llama-bench','-m',path,'-ngl','99','-fa','on','--delay','1','-r',reps,'-o','csv']+targs,capture_output=True,text=True,env=e).stdout
        for row in csv.DictReader(io.StringIO(out)):
            t='pp'+row['n_prompt'] if row['n_prompt']!='0' else 'tg'+row['n_gen']
            res[lab].setdefault(t,[]).append(float(row['avg_ts']))
            meta[lab]=(row.get('model_size'),row.get('model_n_params'),row.get('model_type'))
    print(f'round {r+1}/{rounds} done  gpu: {gpu()}',flush=True)
base=variants[0][0]
for lab,_ in variants:
    sz,np_,mt=meta.get(lab,('?','?','?'))
    bpw = (int(sz)*8/int(np_)) if sz not in (None,'?') and np_ not in (None,'?') else None
    print(f"-- {lab}: size={int(sz)/1e9:.2f} GB  params={int(np_)/1e9:.2f} B  bpw={bpw:.2f}  type={mt}" if bpw else f"-- {lab}: {mt}")
    for t,v in res[lab].items():
        b=st.mean(res[base][t])
        print(f'{lab:14s} {t:7s} mean={st.mean(v):9.2f}  ({100*(st.mean(v)/b-1):+5.1f}% vs {base})  min={min(v):9.2f} max={max(v):9.2f}  n={len(v)}')
