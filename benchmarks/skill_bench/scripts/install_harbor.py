#!/usr/bin/env python3
"""Install the authoritative fixed source into an explicitly selected venv."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
from skill_bench.backends.harbor import SOURCE_SHA


def validate_source(source):
    source = Path(source).resolve()
    def git(*args, binary=False):
        return subprocess.check_output(['git', '-C', str(source), *args], text=not binary, timeout=20)
    remote = git('remote', 'get-url', 'origin').strip()
    if remote not in {'https://github.com/harbor-framework/harbor', 'https://github.com/harbor-framework/harbor.git'}:
        raise ValueError('Source cache must be the official Harbor Git repository.')
    if git('rev-parse', 'HEAD').strip() != SOURCE_SHA:
        raise ValueError('Source cache HEAD must equal the exact approved commit.')
    if git('status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('Source cache contains modified or untracked files.')
    tree = git('ls-tree', '-rz', SOURCE_SHA, '--', 'pyproject.toml', 'README.md', 'LICENSE', 'src', binary=True)
    checked = {}
    for record in tree.split(b'\0'):
        if not record:
            continue
        metadata, raw_name = record.split(b'\t', 1)
        mode, kind, object_id = metadata.split(); name = raw_name.decode(); path = source / name
        if mode not in {b'100644', b'100755'} or kind != b'blob' or path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError('Source cache is incomplete or contains linked/special files.')
        data = path.read_bytes()
        if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != object_id.decode():
            raise ValueError('Source cache bytes differ from the approved Git object.')
        checked[name] = hashlib.sha256(data).hexdigest()
    if not {'pyproject.toml', 'README.md', 'LICENSE', 'src/harbor/job.py'} <= set(checked):
        raise ValueError('Source cache lacks the required build/runtime files.')
    return {'official_url': remote, 'source_sha': SOURCE_SHA, 'verified_files': len(checked),
            'source_files_sha256': hashlib.sha256(json.dumps(checked, sort_keys=True).encode()).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Existing official checkout at the exact approved SHA; no automatic clone.')
    parser.add_argument('--venv', required=True, type=Path, help='Existing explicit virtual environment; global Python is rejected.')
    parser.add_argument('--install', action='store_true', help='Install the verified source and validate actual installed module bytes. Default: validate and print the command only.')
    parser.add_argument('--timeout', type=int, default=180, help='Installation timeout in seconds, between 1 and 600.')
    args = parser.parse_args(argv)
    try:
        proof = validate_source(args.source)
        venv = args.venv.absolute()
        if venv.is_symlink() or not (venv / 'pyvenv.cfg').is_file() or not (venv / 'bin/python').is_file():
            raise ValueError('Target must be an existing explicit virtual environment.')
        if not 1 <= args.timeout <= 600:
            raise ValueError('Installation timeout must be between 1 and 600 seconds.')
        command = ['uv', 'pip', 'install', '--no-sources', '--python', str(venv / 'bin/python'), str(args.source.resolve())]
        result = {'installed': False, 'model_called': False, 'source': proof, 'command': command}
        if args.install:
            subprocess.run(command, check=True, timeout=args.timeout)
            environment = {**os.environ, 'PYTHONPATH': str(SRC)}
            code = 'import json; from skill_bench.backends.harbor import runtime_check; print(json.dumps(runtime_check({})))'
            installed = subprocess.check_output([str(venv / 'bin/python'), '-c', code], env=environment, text=True, timeout=30)
            result.update(installed=True, provenance=json.loads(installed))
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'installed': False, 'model_called': False, 'error': str(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
