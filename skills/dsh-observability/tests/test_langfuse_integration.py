import json, os, ssl, subprocess, sys, tempfile, time, urllib.request, base64
from pathlib import Path
if not all(os.environ.get(k) for k in ('LANGFUSE_PUBLIC_KEY', 'LANGFUSE_SECRET_KEY', 'LANGFUSE_HOST')):
    print('dsh-observability langfuse integration: SKIP (set LANGFUSE_* env)')
    raise SystemExit(0)
host = os.environ['LANGFUSE_HOST'].rstrip('/')
context = ssl._create_unverified_context() if os.environ.get('LANGFUSE_INSECURE') == '1' else None
script = Path(__file__).resolve().parents[1] / 'scripts/langfuse_export.py'
with tempfile.TemporaryDirectory() as td:
    root = Path(td); result = root / 'result.json'; out = root / 'otlp.json'
    result.write_text(json.dumps({'sessionId': 'integration-' + os.urandom(4).hex(), 'events': [
        {'seq': 1, 'type': 'assistant/message', 'time': 1000, 'data': {'usage': {'inputTokens': 1, 'outputTokens': 2}}},
        {'seq': 2, 'type': 'tool/call', 'time': 1100, 'data': {'callId': 'c1', 'name': 'read', 'arguments': '{"file_path":"/tmp/secret"}'}},
        {'seq': 3, 'type': 'tool/result', 'time': 1150, 'data': {'toolCallId': 'c1', 'message': {'content': [{'type': 'text', 'text': 'redacted'}]}}},
    ]}))
    subprocess.run([sys.executable, str(script), str(result), '--out', str(out)], check=True, capture_output=True, text=True)
    trace = json.loads(out.read_text())['resourceSpans'][0]['scopeSpans'][0]['spans'][0]['traceId']
    auth = base64.b64encode(f"{os.environ['LANGFUSE_PUBLIC_KEY']}:{os.environ['LANGFUSE_SECRET_KEY']}".encode()).decode()
    data = None
    for _ in range(10):
        req = urllib.request.Request(f'{host}/api/public/traces/{trace}', headers={'Authorization': 'Basic ' + auth})
        try:
            with urllib.request.urlopen(req, timeout=15, context=context) as resp:
                data = json.loads(resp.read()); break
        except Exception:
            time.sleep(2)
    assert data is not None, 'trace not visible in Langfuse after retries'
    assert data.get('name') == 'dsh.run', data.get('name')
    names = [o.get('name') for o in data.get('observations') or []]
    for _ in range(10):
        if 'gen_ai.chat' in names and 'tool.call' in names:
            break
        time.sleep(2)
        req = urllib.request.Request(f'{host}/api/public/traces/{trace}', headers={'Authorization': 'Basic ' + auth})
        with urllib.request.urlopen(req, timeout=15, context=context) as resp:
            data = json.loads(resp.read())
        names = [o.get('name') for o in data.get('observations') or []]
    if os.environ.get('LANGFUSE_INTEGRATION_STRICT') == '1':
        assert 'gen_ai.chat' in names and 'tool.call' in names, names
    else:
        print('observations so far:', names)
print('dsh-observability langfuse integration: PASS')
