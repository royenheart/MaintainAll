"""Run one Codex CLI arm in the allowlist jail with a short-lived auth window."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolate  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
CODEX = Path(shutil.which('codex') or '')
AUTH_SOURCE = Path.home() / '.codex' / 'auth.json'
CONFIG_SOURCE = Path.home() / '.codex' / 'config.toml'


def prepare(run: Path, repo: Path, mode: str, prompt: str, skill_dir: Path | None = None) -> None:
    if run.exists():
        shutil.rmtree(run)
    (run / 'repo').mkdir(parents=True)
    shutil.copytree(repo, run / 'repo', dirs_exist_ok=True)
    for name in ('home', 'engine-home', 'codex-home', 'agents'):
        (run / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(AUTH_SOURCE, run / 'codex-home' / 'auth.json')
    shutil.copy2(CONFIG_SOURCE, run / 'codex-home' / 'config.toml')
    skill_sources = [ROOT / 'skills' / 'model-policy']
    if mode == 'with':
        if skill_dir is None:
            raise SystemExit('--skill-dir is required for the with arm')
        skill_sources.append(skill_dir)
    for src in skill_sources:
        dst = run / 'repo' / '.agents' / 'skills' / src.name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / 'SKILL.md', dst / 'SKILL.md')
        for sub in ('references', 'scripts', 'templates', 'assets'):
            if (src / sub).is_dir():
                shutil.copytree(src / sub, dst / sub, dirs_exist_ok=True)
    (run / 'prompt.txt').write_text(prompt)


def bwrap(run: Path) -> list[str]:
    args = isolate.build(run, with_skill=False)
    # Keep the host auth visible only to the Codex process; the supervisor revokes it.
    for key, value in {
        'HOME': '/work/home',
        'CODEX_HOME': '/work/codex-home',
        'PATH': f'/work/bin:{isolate.NODE.parent}:/usr/bin:/bin',
    }.items():
        args += ['--setenv', key, value]
    return args


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--prompt', required=True, type=Path)
    p.add_argument('--mode', choices=['with', 'without'], required=True)
    p.add_argument('--model', default='gpt-6-astra')
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--timeout-ms', type=int, default=1_200_000)
    p.add_argument('--skill-dir', type=Path)
    a = p.parse_args()
    run = a.out.resolve()
    prepare(run, a.repo.resolve(), a.mode, a.prompt.read_text(), a.skill_dir.resolve() if a.skill_dir else None)
    cmd = bwrap(run) + [
        str(CODEX), 'exec', '--json', '-C', '/work/repo', '-s', 'workspace-write', '--skip-git-repo-check',
        '-m', a.model, '-c', 'model_reasoning_effort="high"',
        '-o', '/work/final.md', a.prompt.read_text(),
    ]
    started = time.time()
    events_path = run / 'codex-events.jsonl'
    out = open(events_path, 'w')
    proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.PIPE, text=True)
    auth = run / 'codex-home' / 'auth.json'
    # Revoke the auth file after the CLI has read it; keep revoking refreshes.
    deadline = started + 3
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.05)
    while proc.poll() is None:
        for candidate in (auth, run / 'codex-home' / 'auth.json'):
            try:
                candidate.chmod(0)
            except FileNotFoundError:
                pass
        time.sleep(0.2)
    _, stderr = proc.communicate(timeout=max(1, a.timeout_ms / 1000 - (time.time() - started)))
    out.close()
    stdout = events_path.read_text()[-6000:]
    summary = {
        'mode': a.mode, 'model': a.model, 'wall_ms': int((time.time() - started) * 1000),
        'exit': proc.returncode, 'stdout': stdout[-6000:], 'stderr': stderr[-6000:],
        'final': (run / 'final.md').read_text()[:8000] if (run / 'final.md').is_file() else '',
        'codex_events': str(events_path),
    }
    (run / 'run.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ('mode', 'model', 'wall_ms', 'exit')}, indent=2))
    return 0 if proc.returncode == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
