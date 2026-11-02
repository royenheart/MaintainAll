import json, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
script = Path(__file__).resolve().parents[1] / 'scripts/export_otlp.py'
class Handler(BaseHTTPRequestHandler):
    mode = 'partial'
    def do_POST(self):
        length = int(self.headers.get('content-length') or 0)
        self.rfile.read(length)
        if self.mode == 'redirect':
            self.send_response(302); self.send_header('Location', 'http://127.0.0.1:9/x'); self.end_headers(); return
        body = json.dumps({'partialSuccess': {'rejectedSpans': '1', 'errorMessage': 'rejected'}}).encode()
        self.send_response(200); self.send_header('content-type', 'application/json'); self.send_header('content-length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
def run(mode):
    Handler.mode = mode
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    with tempfile.TemporaryDirectory() as td:
        result = Path(td) / 'result.json'
        result.write_text(json.dumps({'sessionId': 'http-test', 'events': [{'seq': 1, 'type': 'assistant/message', 'time': 1000, 'data': {'usage': {'inputTokens': 1, 'outputTokens': 1}}}]}))
        proc = subprocess.run([sys.executable, str(script), str(result), '--endpoint', f'http://127.0.0.1:{server.server_port}'], capture_output=True, text=True)
    server.shutdown()
    return proc
assert run('partial').returncode == 1, 'rejected spans must fail'
r = run('redirect')
assert r.returncode == 1, 'redirect must not be followed'
assert 'error:' in r.stderr
print('dsh-observability otlp http test: PASS')
