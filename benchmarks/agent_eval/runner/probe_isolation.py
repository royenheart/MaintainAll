"""Credential-free isolation probes. No model call; exits nonzero on contamination."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolate  # noqa: E402

PROBE_NAME = 'probe-skill'
PROBE_SOURCE = Path(__file__).resolve().parents[1] / 'probe-skill'
BASELINE = Path(__file__).resolve().parents[3] / 'skills' / 'model-policy'

PROBE = r'''
set -eu
echo "cwd=$(pwd)"
test -d /work/repo
test -w /work/home
test -x /work/bin/dsh
/work/bin/dsh --version >/dev/null
find / -path '*probe-skill*' 2>/dev/null | sed 's#^#FOUND #'
find / -path '*cordis-plugin-development*' 2>/dev/null | sed 's#^#OFFICIAL #'
find / -name 'SKILL.md' 2>/dev/null | wc -l | sed 's#^#SKILLCOUNT #'
'''


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='dsh-probe-') as tmp:
        base = Path(tmp)
        results = {}
        for mode, with_skill in (('without', False), ('with', True)):
            run_dir = base / mode
            isolate.prepare(run_dir, False)
            (run_dir / 'skills' / 'model-policy').mkdir(parents=True, exist_ok=True)
            shutil.copytree(BASELINE, run_dir / 'skills' / 'model-policy', dirs_exist_ok=True)
            if with_skill:
                shutil.copytree(PROBE_SOURCE, run_dir / 'skills' / PROBE_NAME, dirs_exist_ok=True)
            proc = subprocess.run(isolate.build(run_dir, False) + ['bash', '-lc', PROBE], text=True, capture_output=True)
            out = proc.stdout
            found = [line for line in out.splitlines() if line.startswith('FOUND ')]
            official = [line for line in out.splitlines() if line.startswith('OFFICIAL ')]
            skillcount = [line for line in out.splitlines() if line.startswith('SKILLCOUNT ')]
            results[mode] = {
                'exit': proc.returncode,
                'found_skill_paths': found,
                'official_skill_paths': official,
                'skill_count': skillcount,
                'stderr': proc.stderr[-1000:],
            }
        print(json.dumps(results, indent=2))
        without = results['without']
        with_ = results['with']
        ok = (without['exit'] == 0 and not without['found_skill_paths']
              and not without['official_skill_paths']
              and with_['exit'] == 0
              and bool(with_['found_skill_paths'])
              and all(line.startswith('FOUND /work/skills/probe-skill') for line in with_['found_skill_paths'])
              and not with_['official_skill_paths'])
        print('ISOLATION_PROBE', 'PASS' if ok else 'FAIL')
        return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
