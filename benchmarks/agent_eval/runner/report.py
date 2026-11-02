"""Build a per-case observability table from run results (no model calls)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT.parent / 'results'


def metrics_for(run: Path) -> dict:
    result = run / 'result.json'
    if not result.is_file():
        return {}
    return json.loads(subprocess.run([sys.executable, str(ROOT / 'metrics.py'), str(result)], capture_output=True, text=True).stdout)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path)
    p.add_argument('--glob', default='*')
    args = p.parse_args()
    rows = []
    for run in sorted(RESULTS.glob(args.glob)):
        if not run.is_dir() or not (run / 'case-result.json').is_file():
            continue
        cr = json.loads((run / 'case-result.json').read_text())
        grade = cr.get('grade') or {}
        m = metrics_for(run) or cr.get('metrics') or {}
        t = m.get('tokens') or {}
        rows.append({
            'run': run.name,
            'case': cr.get('case') or grade.get('case') or run.name,
            'mode': cr.get('mode') or '',
            'score': f"{grade.get('score')}/{grade.get('max')}",
            'calls': m.get('tool_calls'),
            'uncached': (t.get('inputTokens') or 0) + (t.get('outputTokens') or 0),
            'cache_read': t.get('cacheReadTokens'),
            'total': t.get('totalTokens'),
            'cache_hit': m.get('cache_hit_rate'),
            'wall_ms': m.get('wall_ms'),
            'tool_ms': m.get('tool_ms'),
            'tool_p95': m.get('tool_latency_ms_p95'),
            'refs': m.get('reference_reads'),
            'compact': m.get('compaction_events'),
        })
    header = '| run | case | mode | score | calls | uncached | cache read | cache hit | wall ms | tool ms | tool p95 | refs | compact |'
    lines = [header, '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append('| {run} | {case} | {mode} | {score} | {calls} | {uncached} | {cache_read} | {cache_hit} | {wall_ms} | {tool_ms} | {tool_p95} | {refs} | {compact} |'.format(**r))
    text = '\n'.join(lines)
    print(text)
    if args.out:
        args.out.write_text(text + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
