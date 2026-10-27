"""Render the human-authored review; never infer scores from trace keywords."""
import json, csv
from pathlib import Path
root=Path(__file__).parent
a=json.loads((root/'assessments.json').read_text())
tasks=['wal-recovery-ordering','risk-scorer-replay','html-js-filter','rs-archive-clone','bun-sourcemap-leak','production-planning','sound-change-cascade','cargo-flight-dispatch']
dims=['Requirements','Evidence gathering','Decisions','Implementation/tool use','Verification/recovery']
intro='''INDEPENDENT REASONING AND DECISION REVIEW — 2026-10-04
Bonsai versus Qwen: eight tasks, sixteen attempts

The review is complete for the saved trajectories. There are concrete examples of lost task state, repeated ineffective actions, inadequate verification, and failure to deliver partial work. Bonsai exhibits particularly clear repetition on production planning and sound changes. Qwen also suffers serious failures, including a self-inflicted probe defect that led to a false theory about the environment. These observations establish failure behaviors worth targeting; they do not establish that quantization caused them or that either model has a measured rate of degradation with horizon.

SCOPE AND METHOD

Canonical run: oct04-eight-new-tools, Slurm job 5769.
Remote: /mnt/data/private/cmaira/bonsai_perf/harness-v2/runs/oct04-eight-new-tools
Local evidence: this directory, one subdirectory per model-task pair.
Earlier JSON/native pilots are excluded. The review covers all sixteen saved attempts, including the partial Bonsai risk-scorer trajectory that ended in an infrastructure error. Evidence indexing on voodoo ran as Slurm job 5770 inside Docker; this review uses the downloaded evidence. No training or new model attempts were launched.

I reviewed chronological turn indexes for every attempt, selected underlying reasoning/action/observation records, the task instructions, relevant reference implementation sections, and saved verifier results. Long indexes were read in batches; repeated sequences were also checked directly for identical action objects. This is not an exhaustive line-by-line reading of every generated token or a new execution of every test. Citations use T<number> in the matching attempt's turns.json/index.txt; evaluation.json contains the saved verifier traces. Reference code is under ../tasks/<task>/solution, relative to the parent harness directory.

The reviewer is this frontier assistant. This is an independent assessment of the model trajectories, but NOT a blinded or multi-reviewer study: model identities and outcomes were visible. Scores were assigned from evidence, not produced by a keyword classifier. They are subjective ordinal judgments, not calibrated correctness probabilities, comparable reward magnitudes, or estimates of general model capability. A one-point difference should not be treated as statistically meaningful.

RUBRIC

Five dimensions, each 0–4, equal weight, sum out of 20:
  Requirements: fidelity to the actual task and constraints.
  Evidence gathering: informative inspection/probes and interpretation of observations.
  Decisions: testing hypotheses, retaining verified facts, choosing productive next steps.
  Implementation/tool use: translating findings into correct, usable changes and deliverables.
  Verification/recovery: independent checks, handling contradictions/errors, preserving progress, justified completion.

Anchors: 0 = no effective demonstrated result in that dimension or sustained failure; 1 = weak, major unresolved problems; 2 = mixed, useful progress plus substantial gaps; 3 = mostly effective with specific limitations; 4 = strong and consistently supported by the observed evidence. Each score describes the trajectory as a whole; it is not a token-level reward. Implementation credit distinguishes exploratory scripts from the requested deliverable. Length, eloquence, decode speed and elapsed wall time receive no reward or penalty.

Functional scores below are the PREEXISTING equal-weight requirement-group percentages, preserved for traceability. They are not the new process scores and are not always good measures of task utility. Their exact component groups appear in evaluation.json. Missing/timeout-classified checks yield bounds. No model deadline metric is used. The seven budget-exhausted attempts hit the generated-token cap: four Qwen and three Bonsai; they did not exceed it. Actual task constraints involving time—such as flight turnaround or manufacturing due dates—remain correctness requirements.

MAIN FINDINGS

1. A clear Bonsai repeated-action failure, with an important confound.
   Production planning T86–T161 contains 76 consecutive identical action objects. Each rewrites/runs the same inventory checker; successful observations are followed by another claim about unbalanced quotes. At T162 Bonsai finally says it is stuck and changes action. This is directly observed failure to integrate feedback and recover. The loop crosses mechanical compactions after T89, T118 and T147; that makes the model-plus-context-management system the proper unit of attribution. It does not isolate quantization or exclude a serving/template contribution. The harness source journals each response and appends observations, but the server has not undergone a counterfactual replay audit for this review.

2. Qwen has its own concrete, severe decision failure.
   Risk scoring T11/T19 uses --as-of 2026-10-$dT09:00:00Z. Bash interprets dT09 as the variable name; the intended spelling is ${d}T09. Printed labels use $d correctly, disguising the bad actual argument. Qwen interprets these results versus valid literal timestamps as a moving cutoff, and spends many later turns modeling supposed clock dependence. T89 finally confirms the fixed cutoff. The task's scorer source independently contains a fixed 2026-10-15 UTC boundary and permissive timestamp parsing (environment/legacy/legacy_score.c:18,76). This is a strong example for rewarding checking the probe itself before elaborating a theory. The cause is identified by code inspection; no fresh scorer replay was necessary or performed.

3. Short-task defects coexist with long-trajectory problems.
   Bonsai's Bun release pipeline emits the explicitly allowed [private] source-map marker, then rejects it in its own audit. Saved held-out mixed-policy variants report this precise error. It happened in a 16-turn attempt with no compaction. It is a requirement/implementation/verification defect, not evidence requiring a long-horizon explanation. Qwen tested more variants but its literal audit rejected a valid --trace-probe case too.

4. State tracking and closure differ on cargo dispatch.
   Qwen uses 23 decisions / 56,736 generated tokens; Bonsai uses 85 / 239,120. This is token/action accounting, not a speed comparison. Both repair navigation and miss weight-limited fueling and turnaround accounting. Bonsai additionally retains the wrong reserve amount and repeatedly misremembers filenames and JSON field types near completion. Much of the extra work is redundant or faulty self-validation. More tokens did not yield a more complete repair in this pair; one pair cannot establish a horizon-dependent performance curve.

5. The existing functional percentages need semantic interpretation.
   Sound changes: Qwen's 60% group score means schema, ordering consistency and determinism passed. The saved independent verifier gives actual pair accuracy: 267/780 = 34.23% training; 61/168 = 36.31% hidden. Bonsai produced temporary candidate experiments but never saved rules.json/ordering.txt, so the submitted result is missing. Its reported 143/268 applies only to a selected equal-length training subset and is not comparable to Qwen's full-set result.
   HTML: both 50% scores combine successful benign preservation with FAILED browser-execution/XSS checks. Neither sanitizer is established as safe. Qwen's much longer self-testing largely shared its implementation's parser assumptions.
   Production: both 8.33% scores include the unchanged-source-tables check; neither delivered a usable plan. That credit is constraint compliance, not completed planning functionality.
   Archive: both 0% results lack the requested executable, but Qwen recovered real Reed-Solomon/CRC facts that Bonsai did not consolidate. Process credit can distinguish those attempts without pretending an absent program works.

6. A task-interpretation issue and an infrastructure issue must stay separate.
   Production's reference and tests reserve critical BOM rows and schedule one selected routing operation per dispatch. Both models explored full-BOM/all-operation readings of wording such as fully reserved and routing durations. Those stricter readings produce apparent infeasibility. This is a benchmark semantic limitation, not permission to assume the agents should know the hidden convention. Bonsai also guessed family mappings despite program_family being available and used horizon-end expiry/largest-order checks that are stricter than each actual order's needs—separate, concrete model errors.
   Bonsai risk scoring ends after T49 with HTTP 500 in /apply-template during the next prompt-count request. The preceding clipped tool arguments were not executed. Its outcome remains unknown; this is not a completed zero-score model failure. Earlier repeated empty actions and ineffective probes can still be reviewed, with the shorter observation window noted.

7. WAL is mostly repaired, but not conclusively solved by either model.
   Bonsai's held-out failure is specific: a segment durable prefix contains [2, 1] after blocked reservation instead of sorted [1, 2]. Qwen has four timeout-classified checks, including three exceptions raised inside its submitted LogWriter. The current broad timeout classifier may hide a code liveness defect. Preserving the 94.54–100 bound does NOT mean slow decoding caused the exceptions or that Qwen deserves 100. A targeted concurrency replay is needed to resolve that uncertainty; this review does not invent that result.

WHAT THIS SUGGESTS FOR THE LEARNING STRATEGY

The most defensible target from this batch is preserving verified state, reacting to contradictions, and turning partial discoveries into tested deliverables. These are actionable process behaviors, rather than an established generic quantization decay law. A teacher could help identify a decisive next check at the exact states where the student repeats or rationalizes a contradiction. Qwen's own probe failure shows why teacher agreement alone is not an objective correctness reward.

For a future proof of concept, attach structured labels to transitions: observed fact, action taken, result, requirement affected, supported progress/recovery versus unsupported repetition/regression, confidence and attribution (agent, task ambiguity, infrastructure). The cited evidence blocks below provide initial labels. Do not train directly on the summed review scores. A terminal outcome reward plus independently grounded milestone checks can validate whether these labels predict useful improvement. Retain exploration credit, but cap credit for repeated unchanged probes and do not reward plausible explanations contradicted by tool output.

Before using this as a causal quantization experiment, replay selected failure states under controlled serving/context settings; test whether reminders, improved compaction, or teacher next actions rescue them; and evaluate on separate held-out tasks. Fixed points worth replaying: Bonsai production T85, cargo T40, Bun before variant validation; Qwen risk T11/T19 and sound T47. This describes next research work, not work already executed in this review. Training remains deferred as requested.

ATTEMPT COMPARISON

Task                            Functional Qwen       Bonsai          Process Qwen/Bonsai
'''
lines=[intro]
rows=[]
for task in tasks:
 vals=[];totals=[]
 for model in ['qwen','bonsai']:
  ident=f'{model}-{task}';m=json.loads((root/ident/'metadata.json').read_text());ep=root/ident/'evaluation.json'
  e=json.loads(ep.read_text()) if ep.exists() else None
  if e:
   lo=e['score']['lower'];hi=e['score']['upper'];f=f'{lo:.2f}%' if abs(lo-hi)<1e-8 else f'{lo:.2f}–{hi:.2f}%'
  else:lo=hi=None;f='unknown (infra)'
  vals.append(f);totals.append(str(sum(a[ident]['scores']))+('*' if model=='bonsai' and task=='risk-scorer-replay' else ''))
  rows.append(dict(attempt=ident,status=m['status'],turns=m['turn'],generated_tokens=m['generated_tokens'],compactions=len(m['compactions']),functional_lower=lo,functional_upper=hi,process_total=sum(a[ident]['scores']),**dict(zip(dims,a[ident]['scores']))))
 lines.append(f'{task:31} {vals[0]:21} {vals[1]:15} {totals[0]}/20 / {totals[1]}/20\n')
lines.append('\n* Partial trajectory only; not a completed-run ranking. Do not average these ordinal process scores into a capability percentage.\n\nDETAILED ASSESSMENTS AND TURN CITATIONS\n')
for task in tasks:
 for model in ['qwen','bonsai']:
  ident=f'{model}-{task}';v=a[ident];r=next(x for x in rows if x['attempt']==ident)
  block=[f'\n{ident}\n'+('-'*len(ident))+'\n',f"Status: {r['status']}; {r['turns']} decisions; {r['generated_tokens']:,} generated tokens; {r['compactions']} compactions.\n",'Scores: '+', '.join(f'{d} {s}/4' for d,s in zip(dims,v['scores']))+f". Total {sum(v['scores'])}/20.\n",f"Confidence: {v['confidence']}.\n",v['finding']+'\n',v['reference_comparison']+'\n']
  for e in v['evidence']:
   block.append('  '+e['label'].upper()+' ['+', '.join('T'+str(t) for t in e['turns'])+']: '+e['reason']+'\n')
  block.append(f'Sources: {ident}/turns.json; {ident}/index.txt; {ident}/metadata.json; '+(f'{ident}/evaluation.json' if (root/ident/'evaluation.json').exists() else f'{ident}/error.json')+'.\n')
  txt=''.join(block);(root/ident/'review.txt').write_text(txt);lines.append(txt)
lines.append('''
LIMITS AND UNFINISHED EXPERIMENTS

This completes the requested review of the saved attempts, not a new training or recovery experiment. No new benchmark runs, per-token teacher KL, teacher continuation experiments, server/template counterfactuals or blinded second-reviewer reliability measurements were performed here. WAL timeout attribution remains unresolved, and the Bonsai risk-scorer outcome remains missing. No final conclusion that quantization caused long-horizon degradation is warranted from eight tasks and one attempt per model/task.

Machine-readable human assessments: assessments.json.
Comparison table: comparison.csv.
Every per-attempt directory contains review.txt and the underlying saved evidence.
''')
(root/'REPORT.txt').write_text(''.join(lines))
with (root/'comparison.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print(f'Rendered {len(rows)} reviews, {sum(r["turns"] for r in rows)} archived turns, REPORT.txt ({(root/"REPORT.txt").stat().st_size:,} bytes)')
