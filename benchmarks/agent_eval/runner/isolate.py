"""Allowlist-root bubblewrap jail for one dsh plugin trial."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

BWRAP = shutil.which('bwrap') or '/usr/bin/bwrap'
HARNESS = Path(os.environ.get('DSH_HARNESS_ROOT', str(Path.home() / 'softwares/deepseek-harness'))).resolve()
NVM = Path(os.environ.get('DSH_NVM_ROOT', str(Path.home() / '.nvm'))).resolve()
_candidates = sorted(NVM.glob('versions/node/*/bin/node'))
NODE = Path(os.environ.get('DSH_NODE', str(_candidates[-1] if _candidates else (shutil.which('node') or '/usr/bin/node'))))
REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_NAME = os.environ.get('BENCH_SKILL_NAME', '')
SKILL_SOURCE = Path(os.environ['BENCH_SKILL_SOURCE']).resolve() if os.environ.get('BENCH_SKILL_SOURCE') else (REPO_ROOT / 'skills' / SKILL_NAME if SKILL_NAME else None)


def build(run_dir: Path, with_skill: bool, skill_name: str | None = None, skill_source: Path | None = None, outer_devices: bool = False) -> list[str]:
    """Return the bwrap argv for a fresh trial; the host home is absent by construction."""
    run_dir = run_dir.resolve()
    if outer_devices and not (Path('/dev/nvidia0').exists() and Path('/dev/dri').exists()):
        raise RuntimeError('outer_devices requested but host GPU/DRI nodes are missing')
    args = [
        BWRAP, '--die-with-parent', '--tmpfs', '/',
        '--ro-bind', '/usr', '/usr',
        '--ro-bind', '/bin', '/bin',
        *(['--ro-bind', str(run_dir / 'bin' / 'bash'), '/bin/bash'] if (run_dir / 'bin' / 'bash').is_file() else []),
        '--ro-bind', '/lib', '/lib',
        '--ro-bind', '/lib64', '/lib64',
        '--ro-bind', '/etc', '/etc',
        # The dsh host sandbox keeps a read-only /sys; the benchmark jail mirrors
        # that so a sandbox-awareness trial sees host kernel evidence but no devices.
        '--ro-bind', '/sys', '/sys',
        '--ro-bind', str(HARNESS), str(HARNESS),
        '--ro-bind', str(NVM), str(NVM),
        # The harness ships an official plugin-development skill; mask it so the
        # intervention is the only skill in both arms. Declare any other baseline.
        '--tmpfs', str(HARNESS / 'packages/preset/agent-preset/skills'),
        '--tmpfs', str(HARNESS / '.agents'),
        '--bind', str(run_dir), '/work',
        '--tmpfs', '/work/harness',
        '--tmpfs', '/tmp',
        '--dev', '/dev',
        '--proc', '/proc',
        '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--unshare-cgroup',
        *(['--dev-bind', '/dev/nvidia0', '/dev/nvidia0', '--dev-bind', '/dev/dri', '/dev/dri',
           '--dev-bind-try', '/dev/nvidiactl', '/dev/nvidiactl', '--dev-bind-try', '/dev/nvidia-uvm', '/dev/nvidia-uvm']
          if outer_devices else []),
        '--setenv', 'HOME', '/work/home',
        '--setenv', 'DSH_HOME', '/work/engine-home',
        '--setenv', 'DSH_AGENTS_HOME', '/work/agents',
        '--setenv', 'PATH', f'/work/bin:{NODE.parent}:/usr/bin:/bin:/usr/local/bin',
        '--chdir', '/work/repo',
    ]
    name = skill_name or SKILL_NAME
    source = skill_source or SKILL_SOURCE
    if with_skill:
        if not name or source is None or not source.is_dir():
            raise ValueError('with_skill requires a declared skill name and source')
        args += ['--ro-bind', str(source), f'/work/skills/{name}']
    return args


def prepare(run_dir: Path, with_skill: bool) -> None:
    """Create the writable side of the jail; never copy credentials here."""
    for name in ('repo', 'home', 'engine-home', 'target-home', 'agents', 'skills', 'bin'):
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    node = str(NODE)
    shim = run_dir / 'bin' / 'dsh'
    shim.write_text(f'#!/bin/sh\nexec {node} {HARNESS}/apps/cli/lib/bin.js "$@"\n')
    shim.chmod(0o755)
    # Bound every shell command so a single hanging probe cannot consume the
    # whole trial budget and starve the other arm.


def run(run_dir: Path, with_skill: bool, script: str, *, check: bool = True, skill_name: str | None = None, skill_source: Path | None = None, outer_devices: bool = False) -> subprocess.CompletedProcess[str]:
    prepare(run_dir, with_skill)
    return subprocess.run(build(run_dir, with_skill, skill_name, skill_source, outer_devices) + ['bash', '-lc', script],
                          text=True, capture_output=True, check=check)
