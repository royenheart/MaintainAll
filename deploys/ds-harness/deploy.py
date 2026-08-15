#!/usr/bin/env python3
"""Deploy the MaintainAll dsh plugin set from `plugins.yaml`.

Each listed plugin is an independent directory containing its own
`install.py`; this script only reads the list and fans out the requested
action, so adding a plugin is a one-entry edit in `plugins.yaml` (plus that
plugin directory's own install.py following the same convention).

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


def load_plugins(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    entries = data.get('plugins')
    if not isinstance(entries, list):
        raise SystemExit(f'{path}: missing top-level `plugins` list')
    plugins: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get('name'), str) or not entry['name']:
            raise SystemExit(f'{path}: plugins[{index}] needs a non-empty `name`')
        if not isinstance(entry.get('path'), str) or not entry['path']:
            raise SystemExit(f'{path}: plugins[{index}] ({entry.get("name")}) needs a `path`')
        plugins.append(entry)
    return plugins


def resolve_dir(entry: dict[str, Any]) -> Path:
    return Path(os.path.expanduser(entry['path'])).expanduser()


def ensure_cloned(entry: dict[str, Any]) -> Path:
    target = resolve_dir(entry)
    if target.is_dir():
        return target
    git_url = entry.get('git')
    if not isinstance(git_url, str) or not git_url:
        raise SystemExit(
            f'{entry["name"]}: {target} does not exist and no `git` URL is configured; '
            f'clone it first or fix `path` in {DEFAULT_PLUGINS_FILE}'
        )
    if shutil.which('git') is None:
        raise SystemExit(f'{entry["name"]}: {target} does not exist and `git` is not on PATH')
    print(f'==> {entry["name"]}: cloning {git_url} -> {target}')
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(['git', 'clone', '--', git_url, str(target)])
    if completed.returncode != 0:
        raise SystemExit(
            f'{entry["name"]}: git clone failed ({completed.returncode}); '
            f'if the repository is not published yet, clone/prepare it manually'
        )
    return target


def run_plugin(entry: dict[str, Any], action: str, args: argparse.Namespace) -> int:
    name = entry['name']
    try:
        target = ensure_cloned(entry)
    except SystemExit as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    install_py = target / 'install.py'
    if not install_py.is_file():
        print(f'error: {name}: {install_py} not found; the plugin must ship its own install.py', file=sys.stderr)
        return 1
    command = [sys.executable, str(install_py), action, '--profile', args.profile]
    if args.skip_build:
        command.append('--skip-build')
    if args.dry_run:
        command.append('--dry-run')
    completed = subprocess.run(command)
    return completed.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=['install', 'uninstall', 'list'])
    parser.add_argument('--plugins', type=Path, default=DEFAULT_PLUGINS_FILE, help='plugin list file')
    parser.add_argument('--profile', default=os.environ.get('DSH_PROFILE', 'web'))
    parser.add_argument('--only', metavar='NAME', help='operate on one named plugin')
    parser.add_argument('--skip-build', action='store_true', help='forward to each install.py')
    parser.add_argument('--dry-run', action='store_true', help='forward to each install.py')
    args = parser.parse_args()

    plugins = load_plugins(args.plugins)
    if args.action == 'list':
        for entry in plugins:
            exists = resolve_dir(entry).is_dir()
            print(f'{entry["name"]}: {entry["path"]}{"" if exists else " (missing)"}')
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
        print(f'\n==== {entry["name"]} ({action}) ====')
        failures += run_plugin(entry, action, args)
    if failures:
        raise SystemExit(f'{failures} plugin(s) failed')
    print(f'\ndone: {len(selected)} plugin(s) {action}ed')


if __name__ == '__main__':
    main()
