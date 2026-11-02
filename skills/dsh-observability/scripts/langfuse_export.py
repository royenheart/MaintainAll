#!/usr/bin/env python3
"""Thin Langfuse OTLP wrapper; no Langfuse SDK or raw-prompt upload."""
import base64, os, subprocess, sys
from pathlib import Path
here = Path(__file__).resolve().parent
if len(sys.argv) < 2:
    raise SystemExit('usage: langfuse_export.py <result.json|session.jsonl> [--out file]')
host = os.environ.get('LANGFUSE_HOST', 'https://cloud.langfuse.com').rstrip('/')
public = os.environ.get('LANGFUSE_PUBLIC_KEY')
secret = os.environ.get('LANGFUSE_SECRET_KEY')
cmd = [sys.executable, str(here / 'export_otlp.py'), sys.argv[1], '--endpoint', host + '/api/public/otel']
if os.environ.get('LANGFUSE_INSECURE') == '1': cmd.append('--insecure')
if '--out' in sys.argv:
    i = sys.argv.index('--out'); cmd += ['--out', sys.argv[i + 1]]
if not (public and secret):
    print('LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY not set; writing OTLP JSON locally instead', file=sys.stderr)
    local = [sys.executable, str(here / 'export_otlp.py'), sys.argv[1], '--offline']
    if os.environ.get('LANGFUSE_INSECURE') == '1': local.append('--insecure')
    if '--out' in sys.argv:
        i = sys.argv.index('--out'); local += ['--out', sys.argv[i + 1]]
    subprocess.run(local, check=True)
    raise SystemExit(0)
env = dict(os.environ)
env['OTEL_EXPORTER_OTLP_HEADERS'] = 'Authorization=Basic ' + base64.b64encode(f'{public}:{secret}'.encode()).decode()
subprocess.run(cmd, check=True, env=env)
