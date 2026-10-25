"""Narrow host broker: declarative capture requests, never arbitrary host commands."""
import json
import os
from pathlib import Path
import re
import time


def contained(root, name, *, exists=False):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('Invalid capture path')
    rel = Path(name)
    if rel.is_absolute() or '..' in rel.parts or rel.parts[0] in {'skill', 'tools', '.visual-requests'}:
        raise ValueError('Capture paths must stay inside solver artifact directories')
    target = root / rel
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError('Capture paths cannot follow symlinks')
    if exists and (not target.is_file() or target.stat().st_nlink != 1 or target.stat().st_size > 8 * 1024 * 1024):
        raise ValueError('Capture source must be a bounded ordinary file')
    return target


class BrowserBroker:
    def __init__(self, workspace, tools, *, maximum=32):
        self.workspace, self.tools = Path(workspace), tools
        self.queue = self.workspace / '.visual-requests'
        self.queue.mkdir(mode=0o700)
        self.queue_fd = os.open(self.queue, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.seen, self.maximum = set(), maximum

    def close(self):
        if self.queue_fd is not None:
            os.close(self.queue_fd)
            self.queue_fd = None

    def service(self, deadline):
        from .browser_namespace import namespace_capture
        from .browser_driver import validate_spec
        if self.queue.is_symlink() or not self.queue.is_dir():
            raise ValueError('Browser request queue was replaced')
        requests = [name for name in os.listdir(self.queue_fd) if name.startswith('request-')]
        if len(requests) > self.maximum:
            raise ValueError('Browser request ceiling exceeded')
        for name in sorted(requests):
            if name in self.seen:
                continue
            self.seen.add(name)
            if not re.fullmatch(r'request-[0-9a-f]{32}\.json', name):
                raise ValueError('Invalid browser request file')
            try:
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.queue_fd)
                with os.fdopen(descriptor, 'rb') as stream:
                    info = os.fstat(stream.fileno())
                    import stat
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
                        raise ValueError('Invalid browser request file')
                    request = json.loads(stream.read(65537))
                if not isinstance(request, dict) or set(request) - {'source', 'output', 'spec'}:
                    raise ValueError('Browser requests cannot choose a command or runtime')
                source = contained(self.workspace, request['source'], exists=True)
                if source.suffix.lower() != '.html':
                    raise ValueError('Browser broker accepts HTML source only')
                output = contained(self.workspace, request['output'])
                if output.exists() or not output.parent.is_dir() or output.is_relative_to(self.workspace / 'inputs'):
                    raise ValueError('Capture output must be new and cannot replace read-only inputs')
                spec = validate_spec(request.get('spec'))
                remaining = min(60, deadline - time.monotonic())
                if remaining < 1:
                    raise ValueError('Trial deadline expired before browser capture')
                proof = namespace_capture(self.workspace, source, output, self.tools, spec=spec, timeout=remaining)
                result = {'passed': proof.get('passed') is True, 'frames': len(proof.get('frames', [])),
                          'interactions': proof.get('interactions') is True,
                          'source_sha256': proof.get('source_sha256'), 'scope': proof.get('scope'),
                          'evidence': output.relative_to(self.workspace).as_posix() + '/evidence.json'}
                if not result['passed']:
                    result['error'] = proof.get('failure', 'Independent browser capture failed')
            except (OSError, ValueError, TimeoutError) as error:
                result = {'passed': False, 'error': str(error)[:1200]}
            response = name.replace('request-', 'response-', 1)
            temporary = '.' + response + '.pending'
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.queue_fd)
            try:
                with os.fdopen(descriptor, 'w') as stream:
                    json.dump(result, stream)
                # Publish complete bytes atomically without replacing a
                # solver-created file or following a response symlink.
                os.link(temporary, response, src_dir_fd=self.queue_fd, dst_dir_fd=self.queue_fd, follow_symlinks=False)
            finally:
                os.unlink(temporary, dir_fd=self.queue_fd)
