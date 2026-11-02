import json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
events = [
    {'type': 'thread.started'},
    {'type': 'item.completed', 'item': {'type': 'command_execution'}},
    {'type': 'item.completed', 'item': {'type': 'agent_message'}},
    {'type': 'turn.completed', 'usage': {'input_tokens': 1000, 'cached_input_tokens': 800, 'output_tokens': 50, 'reasoning_output_tokens': 10}},
]
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / 'events.jsonl'
    p.write_text('\n'.join(json.dumps(e) for e in events))
    out = json.loads(subprocess.run([sys.executable, str(ROOT / 'scripts/codex_metrics.py'), str(p)], capture_output=True, text=True, check=True).stdout)
assert out['usage']['input_tokens'] == 1000
assert out['cache_hit_rate'] == 0.8
assert out['uncached_tokens'] == 200 + 50
assert out['total_tokens'] == 1000 + 50
assert dict(out['items'])['command_execution'] == 1
print('dsh-observability codex test: PASS')
