"""Pure summary metrics over attempts; no grader or model call."""
from __future__ import annotations


def summarize(attempts) -> dict:
    values = []
    invalid = 0
    for attempt in attempts:
        if attempt.outcome == 'scored' and attempt.reward is not None and attempt.max_reward:
            values.append(attempt.reward / attempt.max_reward)
        elif attempt.outcome in ('incomplete', 'infrastructure', 'timeout', 'exception', 'failed'):
            invalid += 1
    return {
        'attempts': len(attempts),
        'scored': len(values),
        'invalid': invalid,
        'mean_normalized': sum(values) / len(values) if values else None,
        'min_normalized': min(values) if values else None,
        'max_normalized': max(values) if values else None,
    }
