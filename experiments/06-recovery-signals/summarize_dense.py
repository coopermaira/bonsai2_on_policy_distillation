import json
import math
import statistics
from pathlib import Path

ROOT = Path('/mnt/data/private/cmaira/bonsai_perf/recovery-study-20261003')
rows = [json.loads(line) for line in (ROOT/'dense-scores.jsonl').read_text().splitlines()]
metadata = json.loads((ROOT/'dense-cases.json').read_text())
groups = []
for case in metadata:
    if 'skipped' in case:
        groups.append(case)
        continue
    selected = [r for r in rows if r['id'] == case['id']]
    assert len(selected) == case['target_tokens']
    assert [r['offset'] for r in selected] == list(range(case['target_tokens']))
    assert all(math.isfinite(r[k]) for r in selected for k in ['kl_teacher_student','kl_student_teacher','js','teacher_logprob','student_logprob'])
    assert all(r['kl_teacher_student'] >= -1e-8 and r['kl_student_teacher'] >= -1e-8 and -1e-8 <= r['js'] <= math.log(2)+1e-8 for r in selected)
    parity = json.loads((ROOT/f"dense-parity-{case['id']}.json").read_text())
    first = selected[0]
    assert first['token'] == parity['token']
    checks = {}
    for native, api in [('teacher','fp16'),('student','bonsai')]:
        difference = abs(first[native+'_logprob']-parity['models'][api]['actual_token_logprob'])
        checks[native] = {'absolute_logprob_difference':difference,
                          'top1_equal':first[native+'_top1']==parity['models'][api]['top1'],
                          'logprob_within_0.1_nat':difference < .1}
    groups.append({**case, 'http_native_parity':checks,
                   'mean_kl_teacher_student':statistics.mean(r['kl_teacher_student'] for r in selected),
                   'mean_kl_student_teacher':statistics.mean(r['kl_student_teacher'] for r in selected),
                   'mean_js':statistics.mean(r['js'] for r in selected),
                   'mean_teacher_logprob':statistics.mean(r['teacher_logprob'] for r in selected),
                   'mean_student_logprob':statistics.mean(r['student_logprob'] for r in selected)})
result = {'cases':groups, 'scored_tokens':len(rows),
          'scope':'six prespecified sample-00 command spans, up to 64 tokens each; feasibility measurement, not evidence of horizon-dependent drift',
          'training_performed':False}
(ROOT/'dense-summary.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
