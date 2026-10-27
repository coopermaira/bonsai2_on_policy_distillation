import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path('/mnt/data/private/cmaira/bonsai_perf/recovery-study-20261003')


def read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def wilson(k, n):
    if not n:
        return None
    z = 1.959963984540054
    p = k / n
    den = 1 + z*z/n
    center = (p + z*z/(2*n))/den
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/den
    return [center-half, center+half]


def auc(scores, labels):
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None
    return sum((a > b) + .5*(a == b) for a in pos for b in neg)/(len(pos)*len(neg))


def main():
    rows = []
    baseline = read(ROOT / 'session-baseline-verification.json')
    source = next((ROOT.parent / 'harbor_jobs/comparison-20260929-065104-bonsai-session-window-debug').glob('*/artifacts/app/app'))
    protected_hashes = {f: hashlib.sha256((source / f).read_bytes()).hexdigest() for f in ['types.py', '__init__.py', 'DESIGN.md']}
    records = {}
    for path in sorted((ROOT / 'rollouts').glob('*.json')):
        if '.partial.' in path.name:
            continue
        d = read(path)
        records[d['id']] = d
        v = d.get('final_verification', {})
        is_music = d['state'] == 'music_evidence'
        violations = []
        if not is_music:
            for name, expected in protected_hashes.items():
                f = ROOT / 'rollouts' / d['id'] / 'app/app' / name
                if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != expected:
                    violations.append(name)
        success = (any(t.get('stream_evidence', {}).get('decoded_stream_observed', False) for t in d['turns'])
                   if is_music else v.get('conservation_passed') == 18 and not violations)
        row = {'id': d['id'], 'state': d['state'], 'model': d['model'], 'sample': d['sample'],
               'turns': len(d['turns']), 'success': success, 'official_passed': v.get('official_passed'),
               'conservation_passed': v.get('conservation_passed'), 'error': bool(d.get('error')),
               'protocol_errors': sum(bool(t.get('protocol_error')) for t in d['turns']),
               'capped_responses': sum(t['response']['choices'][0]['finish_reason'] == 'length' for t in d['turns']),
               'completion_tokens': sum(t['response'].get('usage', {}).get('completion_tokens', 0) for t in d['turns']),
               'protected_file_violations': ','.join(violations)}
        rows.append(row)
    grouped = []
    for state in sorted({r['state'] for r in rows}):
        for model in ['bonsai', 'fp16']:
            group = [r for r in rows if r['state'] == state and r['model'] == model]
            n = len(group)
            k = sum(r['success'] for r in group)
            grouped.append({'state': state, 'model': model, 'n': n, 'successes': k,
                            'rate': k/n if n else None, 'wilson95': wilson(k,n),
                            'errors': sum(r['error'] for r in group),
                            'capped_responses': sum(r['capped_responses'] for r in group),
                            'mean_completion_tokens': statistics.mean(r['completion_tokens'] for r in group) if n else None})
    signal_rows = []
    for item in read(ROOT / 'signals/selection-key.json') or []:
        d = records[item['rollout_id']]
        index = item['turn']
        turn = d['turns'][index]
        before = d['turns'][index-1].get('verification', baseline) if index else baseline
        after = turn.get('verification', {})
        full = read(ROOT / 'signals' / (item['id'] + '.judge-full.json'))
        command = read(ROOT / 'signals' / (item['id'] + '.judge-commands.json'))
        dist = read(ROOT / 'signals' / (item['id'] + '.distribution.json'))
        immediate_repair = None
        if d['state'] != 'music_evidence' and 'conservation_passed' in after:
            immediate_repair = (after['conservation_passed'] > before.get('conservation_passed', 15)
                                or after.get('official_passed', 0) > before.get('official_passed', 3))
        r = {'id': item['id'], 'rollout_id': d['id'], 'state': d['state'], 'model': d['model'],
             'turn': index, 'immediate_test_improvement': immediate_repair,
             'stream_observed': turn.get('stream_evidence', {}).get('decoded_stream_observed'),
             'kl_teacher_student': dist.get('kl_teacher_student'), 'js': dist.get('js')}
        for name, data in [('full', full), ('commands', command)]:
            for field in ['groundedness', 'executability', 'usefulness', 'p_improvement', 'p_repair']:
                r[name+'_'+field] = (data.get('score') or {}).get(field)
        signal_rows.append(r)
    predictive = {}
    for mode in ['full', 'commands']:
        pairs = [(r[mode+'_p_repair'], r['immediate_test_improvement']) for r in signal_rows
                 if isinstance(r[mode+'_p_repair'], (int, float)) and r['immediate_test_improvement'] is not None]
        scores, labels = zip(*pairs) if pairs else ([], [])
        predictive[mode] = {'n': len(pairs), 'positive_labels': sum(labels), 'auroc': auc(scores, labels),
                            'brier': statistics.mean((s-y)**2 for s,y in pairs) if pairs else None,
                            'caveat': 'descriptive in-sample diagnostic on selected actions and two task families; not held-out calibration'}
    differences = [r['full_usefulness']-r['commands_usefulness'] for r in signal_rows
                   if isinstance(r['full_usefulness'], (int,float)) and isinstance(r['commands_usefulness'], (int,float))]
    summary = {'groups': grouped, 'judge_immediate_repair_prediction': predictive,
               'explanation_effect': {'n':len(differences),'mean_full_minus_commands_usefulness':statistics.mean(differences) if differences else None},
               'baseline': {k:baseline.get(k) for k in ['conservation_passed','conservation_total','official_passed']},
               'reference': {k:read(ROOT/'session-fresh-reference-verification.json').get(k) for k in ['conservation_passed','conservation_total','official_passed']},
               'qwen_original_artifact': {k:read(ROOT/'session-qwen-artifact-verification.json').get(k) for k in ['conservation_passed','conservation_total','official_passed']},
               'training_performed': False,
               'limitations': ['selected states, not a long-horizon population study',
                               'model-specific continuations confound action quality with downstream policy; no causal action advantage estimate',
                               'one-token command-boundary KL is not action correctness or trajectory-wide KL',
                               'music stream decoding is an intermediate endpoint, not task completion',
                               'test improvement is not the same as useful information gathering',
                               'final protected files checked; intermediate hashes were not recorded']}
    for name, data in [('rollout-summary.csv', rows), ('signal-summary.csv', signal_rows)]:
        if data:
            with (ROOT/name).open('w') as f:
                writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
