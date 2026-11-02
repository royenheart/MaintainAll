"""Paired comparison for one suite and one set of evaluation identities."""
from __future__ import annotations


def _identity(record) -> tuple:
    m = record.manifest
    return (m.suite, m.case, m.model, m.provider, m.agent_runtime,
            m.prompt_sha256, m.workflow_sha256,
            m.environment.get('case_sha256'), m.environment.get('grader_sha256'), m.environment.get('truth_sha256'),
            m.environment.get('fixture_sha256'), m.environment.get('baseline_skill_sha256'),
            m.budgets.get('max_tool_calls'))


def _mean(records) -> tuple[float | None, int]:
    values = []
    for record in records:
        for attempt in record.attempts:
            if attempt.outcome == 'scored' and attempt.reward is not None and attempt.max_reward:
                values.append(attempt.reward / attempt.max_reward)
            elif attempt.outcome == 'failed':
                values.append(0.0)
    return (sum(values) / len(values) if values else None, len(values))


def paired(records) -> list[dict]:
    cells: dict[tuple, dict[str, list]] = {}
    for record in records:
        key = _identity(record)
        cells.setdefault(key, {}).setdefault(record.manifest.arm, []).append(record)
    out = []
    for key, arms in sorted(cells.items()):
        if 'with' not in arms or 'without' not in arms:
            continue
        if any(value is None for value in key[5:]):
            continue
        a, na = _mean(arms['with'])
        b, nb = _mean(arms['without'])
        if a is None or b is None:
            continue
        out.append({'suite': key[0], 'case': key[1], 'with': a, 'without': b,
                    'delta': a - b, 'with_trials': na, 'without_trials': nb})
    return out


def summarize(records) -> dict:
    pairs = paired(records)
    if len(pairs) < 3:
        verdict = 'not-comparable'
    else:
        mean = sum(item['delta'] for item in pairs) / len(pairs)
        variance = sum((item['delta'] - mean) ** 2 for item in pairs) / (len(pairs) - 1)
        se = (variance / len(pairs)) ** 0.5
        cutoffs = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}
        cutoff = cutoffs.get(len(pairs) - 1, 2.201 if len(pairs) == 12 else 2.0)
        verdict = ('with-better' if mean > cutoff * se else
                   'without-better' if mean < -cutoff * se else 'inconclusive')
    return {'paired_cases': len(pairs),
            'mean_delta': (sum(item['delta'] for item in pairs) / len(pairs)) if pairs else None,
            'verdict': verdict, 'pairs': pairs}
