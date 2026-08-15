#!/usr/bin/env python3
"""Deploy the MaintainAll dsh plugin set from `plugins.yaml`.

Each entry declares the git URL `dsh plugin add` should receive. The happy
path is a direct git-hosted install; if that fails the repository is cloned
to `fallback_dir` (default `/tmp/dsh-plugins/<name>`) and installed with
`dsh plugin add file:<dir>` — the local checkout is only an install input,
not a runtime reference, so it can stay in /tmp and be removed later.

No maintainall.yml or cordis:include entry is maintained: every plugin in the
list is a dsh profile bundle (`dsh.bundle.patch`) and `dsh plugin add`
reconciles it into `dsh.profile.bundles` automatically.

Usage:
  python3 deploy.py install    [--profile web] [--only NAME] [--skip-build] [--dry-run]
  python3 deploy.py uninstall  [--profile web] [--only NAME] [--dry-run]
  python3 deploy.py list
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the operator's Python env
    print('error: PyYAML is required (`pip install pyyaml`)', file=sys.stderr)
    raise SystemExit(1)

DEFAULT_PLUGINS_FILE = Path(__file__).resolve().parent / 'plugins.yaml'
DEFAULT_FALLBACK_ROOT = Path('/tmp/dsh-plugins')


def load_plugins(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    entries = data.get('plugins')
    if not isinstance(entries, list):
        raise SystemExit(f'{path}: missing top-level `plugins` list')
    plugins: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get('name'), str) or not entry['name']:
            raise SystemExit(f'{path}: plugins[{index}] needs a non-empty `name`')
        if not isinstance(entry.get('git'), str) or not entry['git']:
            raise SystemExit(f'{path}: plugins[{index}] ({entry.get("name")}) needs a `git` URL')
        plugins.append(entry)
    return plugins


def entry_field(entry: dict[str, Any], key: str, default: Any) -> Any:
    value = entry.get(key)
    return default if value is None else value


def fallback_dir(entry: dict[str, Any]) -> Path:
    configured = entry_field(entry, 'fallback_dir', None)
    if configured is not None:
        return Path(os.path.expanduser(str(configured))).expanduser()
    return DEFAULT_FALLBACK_ROOT / entry['name']


def dsh_command() -> list[str]:
    if shutil.which('dsh') is not None:
        return ['dsh']
    if shutil.which('npx') is not None:
        return ['npx', '@deepseek-ai/dsh']
    raise SystemExit('neither `dsh` nor `npx` found on PATH')


def print_command(command: list[str], cwd: Path | None = None) -> None:
    prefix = f'(cd {cwd} &&) ' if cwd is not None else ''
    print(f'$ {prefix}{" ".join(command)}')


def run(command: list[str], *, dry_run: bool, cwd: Path | None = None) -> int:
    print_command(command, cwd)
    if dry_run:
        return 0
    completed = subprocess.run(command, cwd=cwd)
    return completed.returncode


def dsh_add(spec: str, args: argparse.Namespace) -> int:
    return run([*dsh_command(), 'plugin', '--profile', args.profile, 'add', spec], dry_run=args.dry_run)


def dsh_remove(package: str, args: argparse.Namespace) -> int:
    return run([*dsh_command(), 'plugin', '--profile', args.profile, 'remove', package], dry_run=args.dry_run)


def ensure_fallback_checkout(entry: dict[str, Any], args: argparse.Namespace) -> Path | None:
    target = fallback_dir(entry)
    if target.is_dir() and (target / 'package.json').is_file():
        return target
    if args.dry_run:
        print(f'$ git clone -- {entry["git"]} {target}')
        return target
    if shutil.which('git') is None:
        print(f'error: {entry["name"]}: {target} missing and `git` is not on PATH', file=sys.stderr)
        return None
    print(f'==> {entry["name"]}: cloning {entry["git"]} -> {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(['git', 'clone', '--', entry['git'], str(target)])
    if completed.returncode != 0:
        print(
            f'error: {entry["name"]}: git clone failed ({completed.returncode}); '
            f'if the repository is not published yet, clone/prepare it manually at {target}',
            file=sys.stderr,
        )
        return None
    return target


def install_plugin(entry: dict[str, Any], args: argparse.Namespace) -> int:
    name = entry['name']
    print(f'\n==== {name} (install) ====')
    print(f'==> try direct git install: {entry["git"]}')
    if dsh_add(entry['git'], args) == 0:
        print(f'==> {name} installed from git')
        return 0

    print(f'==> direct git install failed; fall back to a local checkout')
    checkout = ensure_fallback_checkout(entry, args)
    if checkout is None:
        return 1
    install_py = checkout / 'install.py'
    if not install_py.is_file():
        print(f'error: {name}: {install_py} not found; the plugin must ship its own install.py', file=sys.stderr)
        return 1
    command = [
        sys.executable, str(install_py), 'install',
        '--local-dir', str(checkout),
        '--profile', args.profile,
    ]
    if args.skip_build:
        command.append('--skip-build')
    if args.dry_run:
        command.append('--dry-run')
    completed = subprocess.run(command)
    if completed.returncode == 0:
        print(f'==> {name} installed from {checkout} (file:, safe to delete the checkout afterwards)')
    return completed.returncode


def uninstall_plugin(entry: dict[str, Any], args: argparse.Namespace) -> int:
    name = entry['name']
    package = entry_field(entry, 'package', None)
    print(f'\n==== {name} (uninstall) ====')
    if package is None:
        print(f'error: {name}: plugins.yaml entry needs `package` for uninstall', file=sys.stderr)
        return 1
    if dsh_remove(package, args) != 0:
        return 1
    print(f'==> {name} removed')
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=['install', 'uninstall', 'list'])
    parser.add_argument('--plugins', type=Path, default=DEFAULT_PLUGINS_FILE, help='plugin list file')
    parser.add_argument('--profile', default=os.environ.get('DSH_PROFILE', 'web'))
    parser.add_argument('--only', metavar='NAME', help='operate on one named plugin')
    parser.add_argument('--skip-build', action='store_true', help='forward to fallback install.py')
    parser.add_argument('--dry-run', action='store_true', help='print commands without executing')
    args = parser.parse_args()

    plugins = load_plugins(args.plugins)
    if args.action == 'list':
        for entry in plugins:
            target = fallback_dir(entry)
            exists = target.is_dir() and (target / 'package.json').is_file()
            print(f'{entry["name"]}: git={entry["git"]} fallback={target}{"" if exists else " (missing)"}')
        return

    action = args.action or 'install'
    selected = [entry for entry in plugins if args.only is None or entry['name'] == args.only]
    if not selected:
        if args.only is not None:
            raise SystemExit(f'no plugin named "{args.only}" in {args.plugins}')
        print('no plugins configured')
        return

    failures = 0
    for entry in selected:
        failures += install_plugin(entry, args) if action == 'install' else uninstall_plugin(entry, args)
    if failures:
        raise SystemExit(f'{failures} plugin(s) failed')
    print(f'\ndone: {len(selected)} plugin(s) {action}ed')


if __name__ == '__main__':
    main()
