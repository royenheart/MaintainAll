"""Measured aggregate browser limits in a trusted user-manager cgroup scope.

Only the trusted host wrapper reaches the user manager. The child remains the
existing network-disabled bubblewrap command, with no manager credentials mounted.
No per-process address-space limit is presented as an aggregate Chromium RAM cap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import uuid

SYSTEMD_RUN = Path('/usr/bin/systemd-run')
SYSTEMCTL = Path('/usr/bin/systemctl')
MEMORY_BYTES = 1024 * 1024 * 1024
PIDS = 128
MAX_DIAGNOSTIC_BYTES = 65536
ENVIRONMENT = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}


class ScopeOutput(str):
    """Preserve the stdout-string API while carrying independent resource proof."""
    def __new__(cls, content, resource_boundary):
        value = super().__new__(cls, content)
        value.resource_boundary = resource_boundary
        return value


def runtime_directory() -> Path:
    directory = Path('/run/user') / str(os.getuid())
    if directory.is_symlink() or not directory.is_dir() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077 or not (directory / 'bus').is_socket():
        raise ValueError('Browser resource scope user manager is unavailable; no unbounded fallback')
    return directory


def resource_identity() -> dict:
    if not SYSTEMD_RUN.is_file() or not SYSTEMCTL.is_file():
        raise ValueError('Browser resource scope runtime is unavailable; no unbounded fallback')
    return {'method': 'systemd-user-transient-scope', 'executable': str(SYSTEMD_RUN),
            'runtime_sha256': hashlib.sha256(SYSTEMD_RUN.read_bytes()).hexdigest(),
            'control_executable': str(SYSTEMCTL), 'control_sha256': hashlib.sha256(SYSTEMCTL.read_bytes()).hexdigest(),
            'wrapper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'memory_max_bytes': MEMORY_BYTES, 'memory_swap_max_bytes': 0, 'pids_max': PIDS}


def _group(unit: str) -> Path:
    line = next(line for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::'))
    relative = Path(line[3:])
    if relative.name != unit or '..' in relative.parts:
        raise ValueError('Resource wrapper did not enter its exact requested cgroup scope')
    return Path('/sys/fs/cgroup') / str(relative).lstrip('/')


def _observations(group: Path) -> dict:
    result = {}
    for name in ('memory.current', 'memory.peak', 'pids.current', 'pids.peak'):
        path = group / name
        if path.exists():
            result[name] = int(path.read_text().strip())
    for name in ('memory.events', 'pids.events'):
        result[name] = {key: int(value) for key, value in (line.split() for line in (group / name).read_text().splitlines())}
    return result


def _write_report(path: Path, result: dict):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def _child(unit: str, report: Path, arguments: list[str]) -> int:
    """Run only after exact kernel limit readback; report outside child namespace."""
    proof = {'schema_version': 1, 'method': 'systemd-user-transient-scope', 'unit': unit, 'passed': False,
             'scope': 'aggregate cgroup RAM, swap and tasks; does not measure aesthetic or application quality'}
    try:
        group = _group(unit)
        limits = {name: int((group / name).read_text().strip()) for name in ('memory.max', 'memory.swap.max', 'pids.max')}
        proof.update({'cgroup': str(group), 'limits': limits, 'observations': _observations(group)})
        if limits != {'memory.max': MEMORY_BYTES, 'memory.swap.max': 0, 'pids.max': PIDS}:
            raise ValueError('Kernel resource scope limits do not match the requested boundary')
        proof['phase'] = 'limits-verified'
        _write_report(report, proof)
        child = subprocess.run(arguments, env=ENVIRONMENT, stdin=subprocess.DEVNULL, capture_output=True)
        proof.update({'phase': 'completed', 'child_returncode': child.returncode, 'observations': _observations(group)})
        if len(child.stdout) > MAX_DIAGNOSTIC_BYTES or len(child.stderr) > MAX_DIAGNOSTIC_BYTES:
            raise ValueError('Isolated browser command exceeded diagnostic output limits')
        proof['passed'] = child.returncode == 0 and not proof['observations']['memory.events'].get('oom', 0) and not proof['observations']['pids.events'].get('max', 0)
        _write_report(report, proof)
        sys.stdout.buffer.write(child.stdout); sys.stderr.buffer.write(child.stderr)
        return child.returncode if child.returncode >= 0 else 1
    except (OSError, ValueError, RuntimeError, StopIteration) as exc:
        proof['failure'] = str(exc)[:500]
        _write_report(report, proof)
        print('Browser resource boundary failed: ' + str(exc)[:500], file=sys.stderr)
        return 1


def _cleanup(unit: str, environment: dict) -> bool:
    """Stop only the unique scope this call created, never a parent service."""
    try:
        subprocess.run([str(SYSTEMCTL), '--user', 'kill', '--kill-whom=all', '--signal=SIGKILL', unit],
                       env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        subprocess.run([str(SYSTEMCTL), '--user', 'stop', unit], env=environment, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        state = subprocess.run([str(SYSTEMCTL), '--user', 'show', '--property=ActiveState', '--value', unit],
                               env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=3)
        return state.returncode == 0 and state.stdout.strip() in {'inactive', 'failed'}
    except (OSError, subprocess.SubprocessError):
        return False


def run_scoped(arguments: list[str], timeout: float) -> ScopeOutput:
    """Run a bounded trusted command; unavailable managers fail before child launch."""
    resource_identity()
    directory = runtime_directory()
    environment = {**ENVIRONMENT, 'XDG_RUNTIME_DIR': str(directory)}
    unit = 'maintainall-browser-' + uuid.uuid4().hex + '.scope'
    with tempfile.TemporaryDirectory(prefix='skill-browser-resource-') as temporary:
        report = Path(temporary) / 'report.json'
        command = [str(SYSTEMD_RUN), '--user', '--scope', '--quiet', '--unit=' + unit,
                   '--property=MemoryMax=' + str(MEMORY_BYTES), '--property=MemorySwapMax=0',
                   '--property=TasksMax=' + str(PIDS), '--property=MemoryAccounting=yes', '--property=TasksAccounting=yes',
                   '--property=TimeoutStopSec=2s', sys.executable, '-I', str(Path(__file__).resolve()),
                   '--child', '--unit', unit, '--report', str(report), '--', *arguments]
        process = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException as exc:
            cleanup = _cleanup(unit, environment)
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=5)
            process.stdout.close(); process.stderr.close()
            proof = json.loads(report.read_text()) if report.is_file() else {'unit': unit, 'passed': False}
            proof.update({'cleanup_verified': cleanup, 'passed': False})
            if isinstance(exc, subprocess.TimeoutExpired):
                failure = TimeoutError('Browser resource scope replay deadline exceeded')
                failure.resource_boundary = proof
                raise failure from exc
            raise
        proof = json.loads(report.read_text()) if report.is_file() else {'unit': unit, 'passed': False, 'failure': 'scope did not produce measured proof'}
        if process.returncode or not proof.get('passed'):
            proof['cleanup_verified'] = _cleanup(unit, environment)
            failure = ValueError('Isolated browser resource command failed: ' + (stderr + stdout)[-1500:])
            failure.resource_boundary = proof
            raise failure
        if len(stdout.encode()) > MAX_DIAGNOSTIC_BYTES or len(stderr.encode()) > MAX_DIAGNOSTIC_BYTES:
            raise ValueError('Isolated browser command exceeded diagnostic output limits')
        return ScopeOutput(stdout, proof)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--unit', required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.child or not re.fullmatch(r'maintainall-browser-[0-9a-f]{32}\.scope', args.unit):
        parser.error('Only an exact evaluator-created scope is accepted')
    arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
    if not arguments:
        parser.error('Missing trusted child command')
    return _child(args.unit, args.report, arguments)


if __name__ == '__main__':
    raise SystemExit(main())
