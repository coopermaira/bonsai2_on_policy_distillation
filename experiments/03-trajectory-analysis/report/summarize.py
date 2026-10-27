#!/usr/bin/env python3
"""Summarize preserved pilot measurements; never invokes either model."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
rows = [json.loads(p.read_text()) for p in sorted((ROOT/'replay-results/probe-results').glob('*.metrics.json'))]
assert len(rows) == 22
assert all(r['vocab_size'] == 248320 and r['underflow_fp16'] == r['underflow_bonsai'] == 0 for r in rows)
fields = ['id','task','response_index','mode','input_tokens','kl_fp16_bonsai_nats','js_nats','top1_match','top10_overlap','top100_overlap']
with (ROOT/'metrics.csv').open('w') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows({k:r[k] for k in fields} for r in rows)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(9,5))
for label, mode, color, marker in [('Continuation start','continuation_start','#2466a8','o'),('Command start, forced Bonsai reasoning','command_boundary','#bc5b21','^')]:
    rs = [r for r in rows if r['mode'] == mode]
    ax.scatter([r['input_tokens'] for r in rs], [r['kl_fp16_bonsai_nats'] for r in rs],label=label,c=color,marker=marker,s=55,alpha=.85)
for task, step, label in [('react-lead-form',10,'React B10'),('interleaved-vigenere',80,'Vigenère B80'),('music-harmony',51,'Music B51')]:
    r = next(r for r in rows if r['task']==task and r['response_index']==step and r['mode']=='continuation_start')
    ax.annotate(label,(r['input_tokens'],r['kl_fp16_bonsai_nats']),xytext=(5,7),textcoords='offset points',fontsize=9)
ax.set_xscale('log')
ax.set_xlabel('Shared input length (tokens; log scale)')
ax.set_ylabel('Full-vocabulary KL(FP16 || Bonsai), nats')
ax.set_title('One next-token distribution at 22 selected positions')
ax.legend(loc='upper right',fontsize=9)
ax.grid(alpha=.2)
fig.text(.08,.01,'Contexts differ in content and task: this does not isolate a context-length effect.',fontsize=9)
fig.tight_layout(rect=(0,.04,1,1))
fig.savefig(ROOT/'distribution-pilot.png',dpi=180)
fig.savefig(ROOT/'distribution-pilot.pdf')

lines = ['# Music counterfactual: one next response','', 'Only archived commands and their real observations differ between arms. Neither newly proposed command was executed.','']
for arm in ['control','intervention']:
    p = ROOT/'replay-results/counterfactual-results'
    d = json.loads((p/f'{arm}-response.json').read_text())
    m = d['choices'][0]['message']
    lines += [f'## {arm.title()}','',f"Completion tokens: {d['usage']['completion_tokens']}; finish: {d['choices'][0]['finish_reason']}.",'','```json',m['content'],'```','','Recorded reasoning:','','```text',m.get('reasoning_content',''),'```','']
(ROOT/'counterfactual-continuations.md').write_text('\n'.join(lines))
print('Wrote metrics.csv, distribution-pilot.png/.pdf, counterfactual-continuations.md')
