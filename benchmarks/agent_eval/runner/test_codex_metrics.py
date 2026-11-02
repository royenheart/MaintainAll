import json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent
events = [
    {'type': 'thread.started', 'thread_id': 't'},
    {'type': 'turn.started'},
    {'type': 'item.completed', 'item': {'type': 'command_execution'}},
    {'type': 'item.completed', 'item': {'type': 'agent_message'}},
    {'type': 'item.completed', 'item': {'type': 'error'}},
    {'type': 'context_compacted', 'reason': 'auto'},
    {'type': 'turn.completed', 'usage': {'input_tokens': 1000, 'cached_input_tokens': 800, 'output_tokens': 50, 'reasoning_output_tokens': 10}},
]
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / 'events.jsonl'
    p.write_text('\n'.join(json.dumps(e) for e in events))
    out = json.loads(subprocess.run([sys.executable, str(ROOT / 'codex_metrics.py'), str(p)], capture_output=True, text=True, check=True).stdout)
assert out['usage']['input_tokens'] == 1000
assert out['cache_hit_rate'] == round(800 / 1800, 3)
assert dict(out['items'])['command_execution'] == 1
assert out['compaction_events'] == 1
print('codex metrics observability test: PASS')
