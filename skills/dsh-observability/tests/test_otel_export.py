import json, os, subprocess, sys, tempfile
from pathlib import Path
script = Path(__file__).resolve().parents[1] / 'scripts/export_otlp.py'
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    result = root / 'result.json'
    result.write_text(json.dumps({
        'sessionId': 'test-session',
        'finalResponse': 'secret prompt should not appear',
        'events': [
            {'seq': 1, 'type': 'request/context', 'time': 1000, 'data': {'model': 'test-model'}},
            {'seq': 2, 'type': 'assistant/message', 'time': 1100, 'data': {'usage': {'inputTokens': 10, 'outputTokens': 5, 'cacheReadTokens': 2, 'cacheWriteTokens': 1}}},
            {'seq': 3, 'type': 'tool/call', 'time': 1200, 'data': {'callId': 'c1', 'name': 'read', 'arguments': '{"file_path":"/home/secret/token.txt"}'}},
            {'seq': 4, 'type': 'tool/result', 'time': 1250, 'data': {'toolCallId': 'c1', 'message': {'content': [{'type': 'text', 'text': 'secret file body'}]}}},
            {'seq': 5, 'type': 'compaction/start', 'time': 1300, 'data': {}},
            {'seq': 6, 'type': 'compaction/summary', 'time': 1310, 'data': {'summary': [{'type': 'text', 'text': 'summary'}]}},
        ],
    }))
    out = root / 'otlp.json'
    subprocess.run([sys.executable, str(script), str(result), '--out', str(out)], check=True, capture_output=True, text=True)
    data = json.loads(out.read_text())
    spans = data['resourceSpans'][0]['scopeSpans'][0]['spans']
    names = [s['name'] for s in spans]
    assert 'dsh.run' in names and 'gen_ai.chat' in names and 'tool.call' in names and 'dsh.compaction' in names, names
    attrs = {a['key']: a['value'] for s in spans for a in s['attributes']}
    assert attrs['gen_ai.usage.input_tokens']['intValue'] == '13'
    assert attrs['dsh.usage.uncached_input_tokens']['intValue'] == '10'
    assert attrs['gen_ai.usage.output_tokens']['intValue'] == '5'
    assert attrs['tool.target_hash']['stringValue']
    blob = json.dumps(data)
    assert '/home/secret' not in blob
    assert 'secret file body' not in blob
    assert 'secret prompt should not appear' not in blob
print('dsh-observability otlp test: PASS')
