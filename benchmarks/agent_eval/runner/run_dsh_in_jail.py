"""Run one dsh trial inside the allowlist jail through the host inference proxy."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolate  # noqa: E402
import proxy  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
RUNNER = Path(__file__).resolve().parent


def prepare(run: Path, repo: Path, mode: str, prompt: str, skill_dir: Path | None = None, seed_home: Path | None = None, extra_patch: Path | None = None, plugin_dir: Path | None = None) -> None:
    if run.exists():
        shutil.rmtree(run)
    (run / 'repo').mkdir(parents=True)
    shutil.copytree(repo, run / 'repo', dirs_exist_ok=True)
    for name in ('home', 'engine-home', 'agents', 'target-home', 'bin', 'skills'):
        (run / name).mkdir(parents=True, exist_ok=True)
    if seed_home is not None and seed_home.is_dir():
        shutil.copytree(seed_home, run / 'home', dirs_exist_ok=True)
    target = run / 'home' / 'profiles' / 'bench'
    target.mkdir(parents=True, exist_ok=True)
    manifest = target / 'package.json'
    if not manifest.is_file():
        manifest.write_text(json.dumps({
            'name': 'dsh-profile-bench', 'private': True,
            'dsh': {'profile': {'bundles': ['@deepseek-ai/dsh-base']}}, 'dependencies': {},
        }, indent=2) + '\n')
    for dep, spec in (json.loads(manifest.read_text()).get('dependencies') or {}).items():
        if not isinstance(spec, str) or not spec.startswith('link:'):
            continue
        source = (target / spec[5:]).resolve()
        dest = target / 'node_modules' / dep
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        dest.symlink_to(source, target_is_directory=True)
    target_patch = repo / 'profile' / 'cordis.patch.yml'
    if not (target / 'cordis.patch.yml').exists():
        if target_patch.is_file():
            (target / 'cordis.patch.yml').write_text(target_patch.read_text())
        else:
            (target / 'cordis.patch.yml').write_text('# USER PATCH SENTINEL\n[]\n')
    (run / 'prompt.txt').write_text(prompt)
    if extra_patch is not None and extra_patch.is_file():
        shutil.copy2(extra_patch, run / 'extra.patch.yml')
    if plugin_dir is not None:
        if not plugin_dir.is_dir():
            raise SystemExit(f'missing plugin dir {plugin_dir}')
        shutil.copytree(plugin_dir, run / 'plugin', dirs_exist_ok=True)
    node = isolate.NODE
    (run / 'bin' / 'dsh').write_text(f'#!/bin/sh\nexec {node} {isolate.HARNESS}/apps/cli/lib/bin.js "$@"\n')
    (run / 'bin' / 'dsh').chmod(0o755)
    (run / 'profile.patch.yml').write_text(
        "- id: skill-filesystem\n  config:\n    includeDefaultRoots: false\n"
        "    customSkillDirs:\n      - /work/skills\n    watch: false\n")
    srcs = {ROOT / 'skills' / 'model-policy': 'model-policy'}
    if mode == 'with':
        if skill_dir is None:
            raise SystemExit('--skill-dir is required for the with arm')
        srcs[skill_dir] = skill_dir.name
    for src, name in srcs.items():
        if not src.is_dir():
            raise SystemExit(f'missing skill {src}')
        dst = run / 'skills' / name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))
    (run / 'harness').mkdir(exist_ok=True)
    shutil.copy2(RUNNER / 'dsh_task.mjs', run / 'harness' / 'dsh_task.mjs')
    (run / 'harness' / 'mode').write_text(mode)


def jail_run(run: Path, mode: str, proxy_port: int, model: str, timeout_ms: int, max_tool_calls: int = 0, outer_devices: bool = False) -> subprocess.CompletedProcess[str]:
    env = {
        'HOME': '/work/home',
        'DSH_HOME': '/work/engine-home',
        'DSH_AGENTS_HOME': '/work/agents',
        'DEEPSEEK_BASE_URL': f'http://127.0.0.1:{proxy_port}/anthropic',
        'DEEPSEEK_API_KEY': 'benchmark-proxy',
        'AB_MODEL': model,
        'AB_MAX_TOKENS': '32768',
        'AB_TIMEOUT_MS': str(timeout_ms),
        'AB_MAX_TOOL_CALLS': str(max_tool_calls),
        'DSH_HARNESS_ROOT': str(isolate.HARNESS),
        'PATH': f'/work/bin:{isolate.NODE.parent}:/usr/bin:/bin:/usr/local/bin',
    }
    base = isolate.build(run, with_skill=False, outer_devices=outer_devices)
    # Bind the immutable runner, not the repo, into the jail.
    insert = base.index('--bind')
    base[insert:insert] = ['--ro-bind', str(run / 'harness'), '/runner']
    for key, value in env.items():
        base += ['--setenv', key, value]
    prep = subprocess.run(base + ['/work/bin/dsh', '--profile', 'sdk', '--dump-config'],
                          capture_output=True, text=True)
    if prep.returncode != 0:
        return prep
    return subprocess.run(base + [str(isolate.NODE), '/runner/dsh_task.mjs'],
                          capture_output=True, text=True, timeout=timeout_ms / 1000 + 120)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--prompt', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--mode', choices=['with', 'without'], required=True)
    p.add_argument('--model', default='deepseek-flash')
    p.add_argument('--timeout-ms', type=int, default=1_200_000)
    p.add_argument('--skill-dir', type=Path)
    p.add_argument('--seed-home', type=Path)
    p.add_argument('--extra-patch', type=Path)
    p.add_argument('--plugin-dir', type=Path)
    p.add_argument('--max-tool-calls', type=int, default=0)
    p.add_argument('--outer-devices', action='store_true')
    args = p.parse_args()
    run = args.out.resolve()
    prepare(run, args.repo.resolve(), args.mode, args.prompt.read_text(), args.skill_dir.resolve() if args.skill_dir else None, args.seed_home, args.extra_patch, args.plugin_dir.resolve() if args.plugin_dir else None)
    started = time.time()
    try:
        with proxy.Proxy() as px:
            proc = jail_run(run, args.mode, px.port, args.model, args.timeout_ms, args.max_tool_calls, args.outer_devices)
        exit_code = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as error:
        exit_code = 124
        stdout = (error.stdout or '')[-4000:] if isinstance(error.stdout, str) else ''
        stderr = (error.stderr or '')[-8000:] if isinstance(error.stderr, str) else ''
    except Exception as error:
        exit_code = 2
        stdout, stderr = '', f'{type(error).__name__}: {error}'
    summary = {
        'mode': args.mode, 'model': args.model, 'wall_ms': int((time.time() - started) * 1000),
        'exit': exit_code, 'stdout': stdout[-4000:], 'stderr': stderr[-8000:],
    }
    result = run / 'result.json'
    found_result = False
    for line in stdout.splitlines():
        if line.startswith('BENCH_RESULT '):
            try:
                result.write_text(json.dumps(json.loads(line[len('BENCH_RESULT '):]), indent=2))
                found_result = True
            except Exception:
                pass
            break
    if result.is_file():
        try:
            summary['trial'] = json.loads(result.read_text())
        except Exception:
            summary['trial_raw'] = result.read_text()[-4000:]
    (run / 'run.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ('mode', 'model', 'wall_ms', 'exit')}, indent=2))
    return 0 if found_result else 1


if __name__ == '__main__':
    raise SystemExit(main())
