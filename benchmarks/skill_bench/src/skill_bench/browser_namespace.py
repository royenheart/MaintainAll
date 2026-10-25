"""Trusted host broker for browser evidence in a private, offline Linux namespace.

Chromium needs local socket operations denied by Codex's general network seccomp
profile. This broker keeps that profile unchanged and launches Chromium only in
a separate bubblewrap namespace. No generated code executes on the host. The
workspace is copied through anchored descriptors, mounted read-only, and the
sole writable host bind is a private capture directory. Publication uses openat
style traversal, so a solver-controlled symlink cannot redirect host writes.
"""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import tempfile
import wave

from .browser_driver import MAX_FRAME_BYTES, MAX_OUTPUT_BYTES, MAX_SPEC_BYTES, png_dimensions, safe_path, validate_spec

BWRAP = Path('/usr/bin/bwrap')
MAX_WORKSPACE_BYTES = 64 * 1024 * 1024
MAX_WORKSPACE_FILES = 2048
MAX_WORKSPACE_FILE_BYTES = 8 * 1024 * 1024
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
ENVIRONMENT = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@lru_cache(maxsize=8)
def _runtime_identity(path: str, size: int, modified: int) -> dict:
    version = subprocess.run([path, '--version'], env=ENVIRONMENT, capture_output=True, text=True, timeout=5, check=True)
    return {'executable': path, 'sha256': digest(Path(path).read_bytes()), 'version': version.stdout.strip()[:160]}


def fingerprint_identity() -> dict:
    """Return the exact namespace runtime and trusted wrapper identity."""
    if not BWRAP.is_file() or not os.access(BWRAP, os.X_OK):
        raise ValueError('Required browser namespace runtime is unavailable; no host fallback')
    info = BWRAP.stat()
    try:
        identity = _runtime_identity(str(BWRAP), info.st_size, info.st_mtime_ns)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('Browser namespace runtime failed its identity check') from exc
    from .browser_resources import resource_identity
    return {**identity, 'method': 'bubblewrap-unshare-all', 'wrapper_sha256': digest(Path(__file__).read_bytes()), 'resource_scope': resource_identity(),
            'network': 'private network namespace without host network or loopback routes',
            'filesystem': 'frozen workspace and runtimes read-only; private capture output writable'}


def relative_path(workspace: Path, value: Path, name: str) -> Path:
    path = Path(value)
    if '..' in path.parts:
        raise ValueError(name + ' parent traversal is forbidden')
    path = path if path.is_absolute() else workspace / path
    try:
        relative = path.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(name + ' must be inside the private workspace') from exc
    if not relative.parts:
        raise ValueError(name + ' cannot be the workspace root')
    return relative


def parent_fd(root_fd: int, parts, *, create=False) -> int:
    descriptor = os.dup(root_fd)
    try:
        for part in parts:
            if part in {'', '.', '..'}:
                raise ValueError('Unsafe directory component')
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            following = os.open(part, DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor); descriptor = following
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def read_file(root_fd: int, relative: Path, *, limit=MAX_WORKSPACE_FILE_BYTES) -> bytes:
    directory = parent_fd(root_fd, relative.parts[:-1])
    try:
        descriptor = os.open(relative.name, FILE_FLAGS, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Workspace inputs must be regular files without hard links')
        if info.st_size > limit:
            raise ValueError('Workspace file exceeds its byte limit')
        with os.fdopen(descriptor, 'rb', closefd=False) as handle:
            content = handle.read(limit + 1)
        if len(content) > limit:
            raise ValueError('Workspace file exceeds its byte limit')
        return content
    finally:
        os.close(descriptor)


def reject_existing(root_fd: int, relative: Path):
    try:
        directory = parent_fd(root_fd, relative.parts[:-1])
    except FileNotFoundError:
        return
    try:
        try:
            os.stat(relative.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise ValueError('Refusing existing output path')
    finally:
        os.close(directory)


def freeze_workspace(root_fd: int, target: Path, *, exclude_top_level=()):
    """Copy only bounded regular data through no-follow directory descriptors."""
    excluded = tuple(exclude_top_level)
    if any(name != 'captures' for name in excluded) or len(set(excluded)) != len(excluded):
        raise ValueError('Only the evaluator-owned top-level captures tree may be excluded')
    target.mkdir(mode=0o700)
    counters = {'files': 0, 'bytes': 0}
    if excluded:
        counters['excluded_top_level'] = list(excluded)

    def visit(descriptor: int, relative: Path, destination: Path):
        for name in sorted(os.listdir(descriptor)):
            if relative == Path() and name in excluded:
                continue
            counters['files'] += 1
            if counters['files'] > MAX_WORKSPACE_FILES:
                raise ValueError('Workspace exceeds file count limit')
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, DIRECTORY_FLAGS, dir_fd=descriptor)
                try:
                    (destination / name).mkdir(mode=0o700)
                    visit(child, relative / name, destination / name)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                content = read_file(descriptor, Path(name))
                counters['bytes'] += len(content)
                if counters['bytes'] > MAX_WORKSPACE_BYTES:
                    raise ValueError('Workspace exceeds total byte limit')
                (destination / name).write_bytes(content)
            else:
                raise ValueError('Workspace contains a symbolic or special file')
    visit(root_fd, Path(), target)
    return counters


def browser_tool(tools: dict) -> tuple[Path, Path]:
    tool = tools.get('browser', {})
    try:
        executable = safe_path(Path(tool['executable']))
        root = safe_path(Path(tool['root']))
    except (KeyError, OSError, ValueError) as exc:
        raise ValueError('A sealed installed browser runtime is required') from exc
    if not executable.is_file() or not os.access(executable, os.X_OK) or not executable.is_relative_to(root):
        raise ValueError('Browser executable must belong to its dedicated installation root')
    if root in {Path('/'), Path('/usr'), Path('/lib'), Path('/lib64'), Path.home()} or any(p in {'.codex', '.ssh', '.agents'} for p in root.parts):
        raise ValueError('Browser runtime cannot grant a host or credential tree')
    if tool.get('sha256'):
        info = executable.stat()
        if binary_digest(str(executable), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != tool['sha256']:
            raise ValueError('Installed browser changed after its runtime identity was sealed')
    return executable, root


@lru_cache(maxsize=8)
def binary_digest(path: str, device: int, inode: int, size: int, modified: int) -> str:
    return digest(Path(path).read_bytes())


def command(stage: Path, frozen: Path, workspace: Path, browser_root: Path, arguments: list[str], *, extra_mounts=()) -> list[str]:
    args = [str(BWRAP), '--unshare-all', '--die-with-parent', '--new-session', '--cap-drop', 'ALL', '--clearenv',
            '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'HOME', '/tmp/home', '--setenv', 'TMPDIR', '/tmp',
            '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/tmp/home', '--ro-bind', '/usr', '/usr']
    for name in ('/lib', '/lib64'):
        path = Path(name)
        if path.is_symlink():
            args.extend(['--symlink', os.readlink(path), name])
        elif path.exists():
            args.extend(['--ro-bind', name, name])
    for name in ('/etc/ld.so.cache', '/etc/fonts'):
        if Path(name).exists():
            args.extend(['--ro-bind', name, name])
    args.extend(['--ro-bind', str(browser_root), str(browser_root), '--ro-bind', str(frozen), str(workspace),
                 '--bind', str(stage / 'output'), '/capture'])
    for source, target in extra_mounts:
        args.extend(['--ro-bind', str(source), str(target)])
    return [*args, '--chdir', str(workspace), '--', *arguments]


def run(arguments: list[str], timeout: float) -> str:
    from .browser_resources import run_scoped
    return run_scoped(arguments, timeout)


def publish(root_fd: int, relative: Path, captured: Path):
    """Publish into a new directory using anchored descriptors, never path copies."""
    parent = parent_fd(root_fd, relative.parts[:-1], create=True)
    try:
        os.mkdir(relative.name, mode=0o700, dir_fd=parent)
        output_fd = os.open(relative.name, DIRECTORY_FLAGS, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        for source in sorted(captured.iterdir()):
            info = source.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Captured evidence contains a nonregular or hard-linked file')
            descriptor = os.open(source.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=output_fd)
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(source.read_bytes())
    finally:
        os.close(output_fd)


def namespace_capture(workspace: Path, source: Path, output: Path, tools: dict, spec: dict | None = None, *, timeout=60, exclude_top_level=()) -> dict:
    """Capture an immutable private copy; publish bounded seals without host code execution."""
    identity = fingerprint_identity()
    workspace = safe_path(Path(workspace))
    source_relative = relative_path(workspace, source, 'Source')
    output_relative = relative_path(workspace, output, 'Output')
    if source_relative.parts[0] in exclude_top_level:
        raise ValueError('The browser source cannot belong to an excluded tree')
    specification = validate_spec(spec)
    if not 6 <= timeout <= 120:
        raise ValueError('Namespace timeout must be between 6 and 120 seconds')
    executable, browser_root = browser_tool(tools)
    descriptor = os.open(workspace, DIRECTORY_FLAGS)
    try:
        reject_existing(descriptor, output_relative)
        original = read_file(descriptor, source_relative)
        original_hash = digest(original)
        with tempfile.TemporaryDirectory(prefix='skill-browser-namespace-') as temporary:
            stage = Path(temporary); frozen = stage / 'workspace'
            counters = freeze_workspace(descriptor, frozen, exclude_top_level=exclude_top_level)
            driver = frozen / 'tools/browser_driver.py'
            expected = tools['browser'].get('driver_sha256') or digest((Path(__file__).parent / 'browser_driver.py').read_bytes())
            if not driver.is_file() or digest(driver.read_bytes()) != expected:
                raise ValueError('Staged trusted browser driver hash does not match')
            if digest((frozen / source_relative).read_bytes()) != original_hash:
                raise ValueError('Source changed while freezing browser inputs')
            (stage / 'output').mkdir(mode=0o700)
            encoded = json.dumps(specification, allow_nan=False).encode()
            if len(encoded) > MAX_SPEC_BYTES:
                raise ValueError('Capture specification exceeds byte limit')
            (stage / 'spec.json').write_bytes(encoded)
            arguments = ['/usr/bin/python3', '-I', str(workspace / 'tools/browser_driver.py'), '--source', str(workspace / source_relative),
                         '--output', '/capture/result', '--browser', str(executable), '--spec', '/capture-spec.json', '--timeout', str(min(90, timeout - 3))]
            execution = run(command(stage, frozen, workspace, browser_root, arguments, extra_mounts=[(stage / 'spec.json', '/capture-spec.json')]), timeout)
            captured = stage / 'output/result'
            evidence_path = captured / 'evidence.json'
            if not evidence_path.is_file() or evidence_path.stat().st_size > 1024 * 1024:
                raise ValueError('Browser returned missing or oversized evidence metadata')
            result = json.loads(evidence_path.read_text())
            if not result.get('passed') or result.get('source_sha256') != original_hash:
                raise ValueError('Browser evidence failed or source seal does not match')
            files = list(captured.iterdir())
            if len(files) > 152 or any(not p.is_file() or p.is_symlink() or p.stat().st_nlink != 1 for p in files):
                raise ValueError('Browser returned unsafe evidence files')
            if sum(p.stat().st_size for p in files) > MAX_OUTPUT_BYTES:
                raise ValueError('Browser evidence exceeds total byte limit')
            frames = result.get('frames', [])
            if not 2 <= len(frames) <= 144:
                raise ValueError('Browser returned an invalid temporal frame count')
            for frame in frames:
                name = frame.get('path', '')
                if not name or Path(name).name != name or not name.endswith('.png'):
                    raise ValueError('Browser frame path escapes its evidence directory')
                path = captured / name
                if path.stat().st_size > MAX_FRAME_BYTES:
                    raise ValueError('Browser frame exceeds its byte limit')
                content = path.read_bytes()
                if digest(content) != frame.get('sha256') or png_dimensions(content) != (frame.get('width'), frame.get('height')):
                    raise ValueError('Browser frame seal or dimensions do not match')
            probe = result.get('audio_probe')
            if specification.get('audio_probe'):
                if not isinstance(probe, dict) or probe.get('mode') != specification['audio_probe']['mode']:
                    raise ValueError('Audio probe condition differs from the frozen specification')
                stimulus = probe.get('stimulus', {})
                if stimulus.get('path') != 'audio-probe.wav':
                    raise ValueError('Evaluator audio stimulus has an unsafe path')
                pcm = captured / 'audio-probe.wav'
                raw = pcm.read_bytes()
                if len(raw) > 1024 * 1024 or len(raw) != stimulus.get('bytes') or digest(raw) != stimulus.get('sha256'):
                    raise ValueError('Evaluator audio stimulus seal does not match')
                with wave.open(str(pcm), 'rb') as stream:
                    if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()) != (1, 2, 16000, 272000):
                        raise ValueError('Evaluator audio stimulus is not the bounded trusted PCM format')
            elif probe is not None:
                raise ValueError('Unexpected audio probe in a non-audio capture')
            expected_files = {'source.html', 'evidence.json', 'browser.log', *(f['path'] for f in frames)}
            if specification.get('audio_probe'):
                expected_files.add('audio-probe.wav')
            if {p.name for p in files} != expected_files:
                raise ValueError('Browser capture contains undeclared evidence files')
            if digest(read_file(descriptor, source_relative)) != original_hash:
                raise ValueError('Source changed during browser capture')
            result['namespace'] = {**identity, 'frozen_workspace': counters, 'generated_code_executed': True}
            if getattr(execution, 'resource_boundary', None):
                result['namespace']['resource_boundary'] = execution.resource_boundary
            evidence_path.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
            publish(descriptor, output_relative, captured)
            return result
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('Browser namespace capture failed: ' + str(exc)[:500]) from exc
    finally:
        os.close(descriptor)


def namespace_doctor(workspace: Path, tools: dict) -> dict:
    """Prove real network/filesystem enforcement with zero model calls."""
    identity = fingerprint_identity()
    workspace = safe_path(Path(workspace))
    source = workspace / 'inputs/source.html'
    executable, browser_root = browser_tool(tools)
    descriptor = os.open(workspace, DIRECTORY_FLAGS)
    original = read_file(descriptor, Path('inputs/source.html'))
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(('127.0.0.1', 0)); listener.listen(1)
        port = listener.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix='skill-browser-namespace-doctor-') as temporary:
            stage = Path(temporary); frozen = stage / 'workspace'
            freeze_workspace(descriptor, frozen); (stage / 'output').mkdir(mode=0o700)
            (stage / 'host-only-marker').write_text('Host-only marker, never mounted into the namespace.')
            script = '''import json,pathlib,socket
checks={}
def denied(name, operation):
 try: operation();checks[name]=False
 except OSError: checks[name]=True
def connect(address, udp=False):
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM if udp else socket.SOCK_STREAM) as s:
  s.settimeout(.5);s.connect(address)
denied('network_denied',lambda:connect(('1.1.1.1',443)))
denied('host_loopback_denied',lambda:connect(('127.0.0.1',PORT)))
denied('udp_denied',lambda:connect(('1.1.1.1',53),True))
denied('host_credentials_denied',lambda:pathlib.Path(AUTH).read_bytes())
denied('host_home_denied',lambda:list(pathlib.Path(HOME).iterdir()))
denied('host_marker_denied',lambda:pathlib.Path(MARKER).read_bytes())
denied('source_readonly',lambda:pathlib.Path(SOURCE).open('ab'))
denied('tools_readonly',lambda:pathlib.Path(DRIVER).open('ab'))
pathlib.Path('/capture/write-proof').write_text('Output is writable.');checks['output_writable']=True
a,b=socket.socketpair()
try:
 a.send(b'safe');checks['unix_socketpair_available']=b.recv(4)==b'safe'
 a.shutdown(socket.SHUT_RD);a.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,4096)
finally: a.close();b.close()
print(json.dumps({'passed':all(checks.values()),'checks':checks}))
'''
            # Host home ancestors can exist as empty mount parents; prove its
            # private configuration content is absent, rather than directory absence.
            replacements = {'PORT': str(port), 'AUTH': repr(str(Path.home() / '.codex/auth.json')),
                            'HOME': repr(str(Path.home() / '.ssh')), 'MARKER': repr(str(stage / 'host-only-marker')), 'SOURCE': repr(str(source)),
                            'DRIVER': repr(str(workspace / 'tools/browser_driver.py'))}
            for key, value in replacements.items():
                script = script.replace(key, value)
            (stage / 'probe.py').write_text(script)
            stdout = run(command(stage, frozen, workspace, browser_root, ['/usr/bin/python3', '-I', '/namespace-probe.py'],
                                 extra_mounts=[(stage / 'probe.py', '/namespace-probe.py')]), 15)
            result = json.loads(stdout)
            if read_file(descriptor, Path('inputs/source.html')) != original:
                raise ValueError('Namespace doctor changed the original source')
            boundary = getattr(stdout, 'resource_boundary', None)
            return {**result, 'namespace': {**identity, **({'resource_boundary': boundary} if boundary else {})}, 'generation_calls': 0}
    finally:
        listener.close(); os.close(descriptor)
