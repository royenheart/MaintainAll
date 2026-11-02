"""Host-side DeepSeek inference proxy: the jail gets a dummy key, never the real one."""
from __future__ import annotations

import http.client
import json
import os
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import yaml

UPSTREAM = 'api.deepseek.com'
ANTHROPIC = '/anthropic'


def real_key() -> str:
    candidates = [Path('~/.dsh/.credentials.yaml').expanduser(),
                  Path(os.environ.get('DSH_HOME', '~/.dsh')).expanduser() / '.credentials.yaml']
    for path in candidates:
        if not path.is_file():
            continue
        data = yaml.safe_load(path.read_text()) or {}
        refs = data.get('refs') or {}
        key = refs.get('DEEPSEEK_API_KEY')
        if isinstance(key, str) and key:
            return key
    raise SystemExit('no DEEPSEEK_API_KEY in the host credential store')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'dsh-bench-proxy'

    def log_message(self, fmt, *args):  # never log headers or bodies
        pass

    def _upstream_path(self) -> str:
        path = urlsplit(self.path).path
        if path == '/models' or path.startswith('/models?'):
            return '/models'
        if path.startswith(ANTHROPIC + '/'):
            return path
        return ''

    def _forward(self) -> None:
        length = int(self.headers.get('content-length') or 0)
        body = self.rfile.read(length) if length else b''
        path = self._upstream_path()
        if not path:
            self.send_error(404)
            return
        headers = {}
        for name, value in self.headers.items():
            low = name.lower()
            if low in ('host', 'content-length', 'x-api-key', 'authorization', 'connection'):
                continue
            headers[name] = value
        headers['x-api-key'] = real_key()
        headers['host'] = UPSTREAM
        conn = http.client.HTTPSConnection(UPSTREAM, 443, context=ssl.create_default_context(), timeout=300)
        try:
            conn.request(self.command, path, body=body, headers=headers)
            upstream = conn.getresponse()
            payload = upstream.read()
            self.send_response(upstream.status)
            for name, value in upstream.getheaders():
                if name.lower() in ('transfer-encoding', 'connection', 'content-length'):
                    continue
                self.send_header(name, value)
            self.send_header('content-length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as error:  # no secrets in the client-visible message
            try:
                self.send_error(502, f'upstream proxy failure: {type(error).__name__}')
            except Exception:
                pass
        finally:
            conn.close()

    def do_GET(self):
        self._forward()

    def do_POST(self):
        self._forward()

    def do_HEAD(self):
        self._forward()


class Proxy:
    def __init__(self) -> None:
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    def __enter__(self) -> 'Proxy':
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def main() -> None:
    with Proxy() as proxy:
        print(json.dumps({'port': proxy.port}))


if __name__ == '__main__':
    main()
