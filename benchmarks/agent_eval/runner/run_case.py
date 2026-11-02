"""Run one frozen case under one arm and grade it outside the jail."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNNER = Path(__file__).resolve().parent
BENCH = Path(__file__).resolve().parents[1]
RESULTS = BENCH / 'results'


def hash_tree(path: Path, exclude: set[str] | None = None, exclude_prefixes: tuple[str, ...] = ()) -> str:
    h = hashlib.sha256()
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    exclude = exclude or set()
    for f in sorted(p for p in path.rglob('*') if p.is_file()):
        rel = f.relative_to(path).as_posix()
        if rel in exclude or any(rel == p or rel.startswith(p + '/') for p in exclude_prefixes):
            continue
        h.update(f.relative_to(path).as_posix().encode())
        h.update(b'\0')
        h.update(f.read_bytes())
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--case', required=True, type=Path)
    p.add_argument('--mode', choices=['with', 'without'], required=True)
    p.add_argument('--model', default='deepseek-flash')
    p.add_argument('--out', type=Path)
    p.add_argument('--timeout-ms', type=int, default=None)
    p.add_argument('--skill-dir', type=Path)
    p.add_argument('--prompt', type=Path)
    p.add_argument('--skill-name', type=str)
    p.add_argument('--seed-home', type=Path)
    p.add_argument('--extra-patch', type=Path)
    p.add_argument('--plugin-dir', type=Path)
    p.add_argument('--max-tool-calls', type=int, default=None)
    args = p.parse_args()
    case_dir = args.case.resolve()
    case = json.loads((case_dir / 'case.json').read_text())
    max_tool_calls = args.max_tool_calls if args.max_tool_calls is not None else int((case.get('budget') or {}).get('max_tool_calls', 0))
    timeout_ms = args.timeout_ms if args.timeout_ms is not None else int(case.get('timeout_ms', 1_200_000))
    run_dir = (args.out or (RESULTS / f"{case['id']}-{args.mode}-{int(time.time())}")).resolve()
    prompt = (args.prompt or (case_dir / case['prompt'])).resolve()
    fixture = (case_dir / case['fixture']).resolve()
    started = time.time()
    report_files = {'plan.md', 'audit.md', 'metrics.md', 'report.md', 'report.json'}
    allowed_files = set(case.get('allow_files') or [])
    allowed_prefixes = tuple(case.get('allow_prefixes') or [])
    fixture_hash = hash_tree(fixture, report_files, allowed_prefixes)
    fixture_compare_hash = hash_tree(fixture, report_files | allowed_files, allowed_prefixes)
    run = subprocess.run([
        sys.executable, str(RUNNER / 'run_dsh_in_jail.py'),
        '--repo', str(fixture), '--prompt', str(prompt), '--out', str(run_dir),
        '--mode', args.mode, '--model', args.model, '--timeout-ms', str(timeout_ms),
        '--max-tool-calls', str(max_tool_calls),
        *(['--outer-devices'] if case.get('outerDevices') else []),
        *(['--skill-dir', str(args.skill_dir)] if args.skill_dir else []),
        *(['--seed-home', str(args.seed_home or (case_dir / case['seedHome']))] if (args.seed_home or case.get('seedHome')) else []),
        *(['--extra-patch', str(args.extra_patch or (case_dir / case['extraPatch']))] if (args.extra_patch or case.get('extraPatch')) else []),
        *(['--plugin-dir', str(args.plugin_dir or (case_dir / case['pluginDir']))] if (args.plugin_dir or case.get('pluginDir')) else []),
    ], text=True, capture_output=True)
    grade_path = (BENCH / case['grader']).resolve()
    graders_root = (BENCH / 'graders').resolve()
    if graders_root not in grade_path.parents:
        raise SystemExit(f'case grader must live under {graders_root}: {grade_path}')
    grade_cmd = ['node', str(grade_path)] if grade_path.suffix == '.mjs' else [sys.executable, str(grade_path)]
    result_file = run_dir / 'result.json'
    trial_payload = json.loads(result_file.read_text()) if result_file.is_file() else {}
    report_present = (run_dir / 'repo' / 'report.json').is_file()
    transport_error = bool(trial_payload.get('error')) and not trial_payload.get('events') and not (trial_payload.get('budget') or {}).get('exceeded')
    for event in reversed(trial_payload.get('events') or []):
        if event.get('type') != 'turn/end':
            continue
        reason = (event.get('data') or {}).get('reason') or {}
        error = reason.get('error') or {}
        code = str(error.get('code', '')).upper()
        if reason.get('kind') == 'error' and (code in {'TRANSPORT', 'RATE_LIMIT', 'AUTH', 'TIMEOUT', 'SERVER', 'QUOTA', 'ACCOUNT_QUOTA', 'EMPTY_RESPONSE'} or code.startswith('HTTP_')):
            transport_error = True
        break
    incomplete = not result_file.is_file() or transport_error
    grade = None
    if run.returncode != 0 or transport_error or (incomplete and not report_present):
        grade_data = {'score': 0, 'max': None, 'error': 'invalid trial: missing result.json/report.json or non-zero run', 'run_exit': run.returncode}
    else:
        grade = subprocess.run(grade_cmd + [str(run_dir / 'repo'), str(run_dir / 'home'), str(case['id'])],
                               text=True, capture_output=True)
        try:
            grade_data = json.loads(grade.stdout)
        except Exception:
            grade_data = {'error': grade.stdout[-2000:] + grade.stderr[-2000:]}
    repo_hash = hash_tree(run_dir / 'repo', report_files | allowed_files, allowed_prefixes)
    fixture_changed = repo_hash != fixture_compare_hash
    score, maximum = grade_data.get('score'), grade_data.get('max')
    if (grade is None or grade.returncode != 0 or not isinstance(score, int) or not isinstance(maximum, int)
            or maximum < 0 or score < 0 or score > maximum):
        grade_data = {'score': 0, 'max': None, 'error': 'invalid grade output', 'grader_exit': grade.returncode if grade is not None else None}
    unsafe_report = any((run_dir / 'repo' / name).is_symlink() for name in report_files)
    if unsafe_report:
        grade_data = {'score': 0, 'max': None, 'error': 'report artifact is a symlink', 'symlink_report': True}
    if fixture_changed:
        grade_data = {'score': 0, 'max': None, 'error': 'fixture mutated outside the expected report', 'fixture_changed': True}
    trial_budget = (json.loads((run_dir / 'result.json').read_text()).get('budget') if (run_dir / 'result.json').is_file() else None)
    if trial_budget and trial_budget.get('exceeded'):
        grade_data = {'score': 0, 'max': 1, 'error': 'tool-call budget exceeded', 'budget': trial_budget}
    if result_file.is_file():
        metrics = subprocess.run([sys.executable, str(RUNNER / 'metrics.py'), str(result_file)],
                                 text=True, capture_output=True)
        try:
            metric_data = json.loads(metrics.stdout)
        except Exception:
            metric_data = {'error': metrics.stdout[-2000:] + metrics.stderr[-2000:]}
    else:
        metric_data = {'error': 'result.json missing; incomplete trial graded from report'}
    prompt_sha256 = hash_tree(prompt)
    sandbox_modes = []
    if result_file.is_file():
        try:
            for event in json.loads(result_file.read_text()).get('events') or []:
                if event.get('type') == 'sandbox/mode':
                    mode = (event.get('data') or {}).get('mode')
                    if mode: sandbox_modes.append(mode)
        except Exception:
            pass
    target_skill = args.skill_dir.name if args.skill_dir else None
    skill_trace = {'loaded': False, 'loaded_skills': [], 'load_idx': None, 'first_probe_idx': None, 'first_mountinfo_idx': None,
                   'ref_reads_any_tool': 0, 'harness_reads': 0, 'skill_calls': 0}
    if result_file.is_file():
        try:
            recorded = json.loads(result_file.read_text())
            contents = []
            for idx, event in enumerate(recorded.get('events') or []):
                if event.get('type') == 'tool/call':
                    data = event.get('data') or {}
                    args_text = str(data.get('arguments') or '')
                    if data.get('name') == 'skill':
                        skill_trace['skill_calls'] += 1
                        try:
                            requested = (json.loads(args_text) or {}).get('name')
                        except Exception:
                            requested = None
                        if requested and requested not in skill_trace['loaded_skills']:
                            skill_trace['loaded_skills'].append(str(requested))
                        if requested == target_skill and skill_trace['load_idx'] is None:
                            skill_trace['load_idx'] = idx
                    if '/skills/' in args_text and ('references/' in args_text or 'SKILL.md' in args_text):
                        skill_trace['ref_reads_any_tool'] += 1
                    if re.search(r'(nvidia-smi|/proc/self/mountinfo|/proc/driver/nvidia|/dev/(?!null)|lspci|lsusb|mountinfo|/sys/class/drm)', args_text, re.I):
                        if skill_trace['first_probe_idx'] is None:
                            skill_trace['first_probe_idx'] = idx
                    if 'mountinfo' in args_text.lower() and skill_trace['first_mountinfo_idx'] is None:
                        skill_trace['first_mountinfo_idx'] = idx
                    if any(x in args_text for x in ('/work/harness', '/runner', 'dsh_task.mjs', 'deepseek-harness')):
                        skill_trace['harness_reads'] += 1
                if event.get('type') == 'tool/result':
                    for block in ((event.get('data') or {}).get('message') or {}).get('content') or []:
                        if isinstance(block, dict) and isinstance(block.get('text'), str):
                            contents.append(block['text'])
            loaded_names = {name for name in skill_trace['loaded_skills'] if f'<skill_content name="{name}"' in '\n'.join(contents)}
            skill_trace['loaded_skills'] = sorted(loaded_names)
            skill_trace['loaded'] = bool(target_skill and target_skill in loaded_names)
        except Exception:
            pass
    result = {
        'case': case['id'], 'skill_trace': skill_trace,
 'version': case['version'], 'mode': args.mode, 'model': args.model,
        'prompt_sha256': prompt_sha256, 'case_scale': case.get('scale'), 'case_split': case.get('split'),
        'max_tool_calls': max_tool_calls, 'sandbox_modes': sandbox_modes,
        'baseline_skill_sha256': hash_tree(ROOT / 'skills' / 'model-policy'),
        'case_sha256': hash_tree(case_dir),
        'grader_sha256': hash_tree(grade_path) if grade is not None else None,
        'expected_sha256': (hash_tree(BENCH/'expected'/(case['id']+'.json')) if (BENCH/'expected'/(case['id']+'.json')).is_file() else None),
        'truth_sha256': (hash_tree(BENCH/'truth'/(case['id']+'.json')) if (BENCH/'truth'/(case['id']+'.json')).is_file() else None),
        'fixture_sha256': fixture_hash,
        'repo_sha256': repo_hash,
        'fixture_changed': fixture_changed,
        'skill_sha256': hash_tree(args.skill_dir.resolve()) if args.skill_dir else None,
        'skill_name': args.skill_name or (args.skill_dir.name if args.skill_dir else None),
        'run_exit': run.returncode, 'incomplete': incomplete, 'grader_exit': grade.returncode if grade is not None else None,
        'grade': grade_data, 'metrics': metric_data,
        'wall_ms': int((time.time() - started) * 1000),
        'stdout': run.stdout[-2000:], 'stderr': run.stderr[-4000:],
    }
    out = run_dir / 'case-result.json'
    import tempfile
    fd, tmp_name = tempfile.mkstemp(prefix='case-result-', suffix='.json', dir=run_dir)
    with open(fd, 'w') as handle:
        handle.write(json.dumps(result, indent=2))
    Path(tmp_name).replace(out)
    print(json.dumps({k: result[k] for k in ('case', 'mode', 'model', 'run_exit', 'wall_ms')}, indent=2))
    print(json.dumps(grade_data, indent=2))
    return 0 if grade_data.get('score') == grade_data.get('max') and grade_data.get('max') is not None else 1


if __name__ == '__main__':
    raise SystemExit(main())
