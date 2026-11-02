import json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
events = [
    {'type': 'turn/start', 'seq': 1, 'time': 1000, 'data': {}},
    {'type': 'step/start', 'seq': 2, 'time': 1000, 'data': {}},
    {'type': 'system/message', 'seq': 3, 'time': 1000, 'data': {'message': {'role': 'system', 'content': [{'type': 'text', 'text': 's' * 100}]}}},
    {'type': 'request/header', 'seq': 4, 'time': 1000, 'data': {'header': {'tools': [{'name': 'read'}]}}},
    {'type': 'request/context', 'seq': 5, 'time': 1000, 'data': {'contextWindow': 1000000}},
    {'type': 'assistant/message', 'seq': 6, 'time': 1100, 'data': {'usage': {'inputTokens': 100, 'outputTokens': 50, 'cacheReadTokens': 200, 'cacheWriteTokens': 0, 'totalTokens': 350}, 'message': {'role': 'assistant', 'content': [{'type': 'reasoning', 'text': 'r' * 20}, {'type': 'text', 'text': 'a' * 10}]}}},
    {'type': 'tool/call', 'seq': 7, 'time': 1200, 'data': {'callId': 'c1', 'name': 'read', 'arguments': json.dumps({'file_path': '/work/skills/x/references/client.md'})}},
    {'type': 'tool/result', 'seq': 8, 'time': 1300, 'data': {'toolCallId': 'c1', 'message': {'role': 'tool', 'content': [{'type': 'text', 'text': 'x' * 40}], 'isError': False}}},
    {'type': 'compaction/summary', 'seq': 9, 'time': 1400, 'data': {'summary': 's' * 100, 'shadowedSeqs': [1, 2]}},
    {'type': 'compaction/prune', 'seq': 10, 'time': 1500, 'data': {'shadowedSeqs': [3]}},
    {'type': 'tool/call', 'seq': 11, 'time': 1600, 'data': {'callId': 'c2', 'name': 'edit', 'arguments': json.dumps({'file_path': '/work/repo/x', 'content': 'y' * 5})}},
    {'type': 'tool/result', 'seq': 12, 'time': 1700, 'data': {'toolCallId': 'c2', 'message': {'role': 'tool', 'content': [{'type': 'text', 'text': 'ok'}], 'isError': False}}},
    {'type': 'step/end', 'seq': 13, 'time': 1800, 'data': {}},
]
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / 'result.json'
    p.write_text(json.dumps({'sessionId': 'test', 'finalResponse': 'ok', 'events': events}))
    out = json.loads(subprocess.run([sys.executable, str(ROOT / 'metrics.py'), str(p)], capture_output=True, text=True, check=True).stdout)
assert out['tokens']['totalTokens'] == 350, out['tokens']
assert out['cache_hit_rate'] == round(200 / 300, 3), out['cache_hit_rate']
assert out['tool_calls'] == 2 and out['tool_errors'] == 0
assert out['tool_latency_ms_p50'] == 100
assert out['reference_reads'] == 1 and out['reference_bytes'] == 40
assert out['compaction_events'] == 2 and out['compaction_summary_chars'] == 100 and out['compaction_shadowed_events'] == 3
assert out['context_window'] == 1000000 and out['tool_schema_bytes'] > 0
assert out['system_prompt_bytes'] > 0 and out['reasoning_chars'] == 20
print('metrics observability test: PASS')
