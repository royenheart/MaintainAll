import json, os, subprocess, sys, tempfile
from pathlib import Path
script = Path(__file__).resolve().parents[1] / 'scripts/langfuse_export.py'
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    result = root / 'result.json'
    result.write_text(json.dumps({'sessionId': 'langfuse-test', 'events': [
        {'seq': 1, 'type': 'assistant/message', 'time': 1000, 'data': {'usage': {'inputTokens': 1, 'outputTokens': 2}}},
    ]}))
    out = root / 'otlp.json'
    env = dict(os.environ)
    env.pop('LANGFUSE_PUBLIC_KEY', None)
    env.pop('LANGFUSE_SECRET_KEY', None)
    env['OTEL_EXPORTER_OTLP_ENDPOINT'] = 'http://127.0.0.1:9/never'
    env['OTEL_EXPORTER_OTLP_HEADERS'] = 'Authorization=Bearer sentinel'
    proc = subprocess.run([sys.executable, str(script), str(result), '--out', str(out)], env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text())
    assert data['resourceSpans'][0]['scopeSpans'][0]['spans']
    assert 'Basic ' not in proc.stdout + proc.stderr
print('dsh-observability langfuse test: PASS')
