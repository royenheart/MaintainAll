"""Adapter: the existing benchmarks/agent_eval cases/results.

The adapter reads the legacy files; it does not move or rewrite them. The unified
record is a projection, and a legacy result is never promoted to a second truth.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json

from ..contracts import Attempt, CaseSpec, Record, RunManifest, SuiteSpec, sha256
from ..metrics import summarize

REPORT_FILES = {'plan.md', 'audit.md', 'metrics.md', 'report.md', 'report.json'}


def tree_hash(path: Path, exclude: set[str] | None = None) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    h = hashlib.sha256()
    exclude = exclude or set()
    for file in sorted(p for p in path.rglob('*') if p.is_file()):
        rel = file.relative_to(path).as_posix()
        if rel in exclude:
            continue
        h.update(rel.encode()); h.update(b'\0'); h.update(file.read_bytes())
    return h.hexdigest()


def load_suite(root: Path) -> SuiteSpec:
    root = Path(root).resolve()
    manifest = json.loads((root / 'datasets' / 'validation-1.json').read_text())
    cases = []
    entries = [(entry, 'cases', entry.get('split', 'control')) for entry in manifest['cases']]
    entries += [(entry, 'holdout', 'holdout') for entry in manifest.get('holdout', [])]
    for entry, base, split in entries:
        case_dir = root / base / entry['id']
        cfg_path = case_dir / 'case.json'
        if not cfg_path.is_file():
            continue
        cfg = json.loads(cfg_path.read_text())
        prompt = case_dir / cfg['prompt']
        fixture = case_dir / cfg['fixture']
        grader = root / cfg['grader']
        truth = root / 'truth' / f"{entry['id']}.json"
        cases.append(CaseSpec(
            case_id=entry['id'], suite='dsh-skills', split=split,
            scale=entry.get('scale') or 'small', prompt_sha256=sha256(prompt.read_bytes()),
            fixture_sha256=tree_hash(fixture, REPORT_FILES), grader_sha256=tree_hash(grader),
            truth_sha256=tree_hash(truth) if truth.is_file() else None,
            description=cfg.get('description', ''),
        ))
    return SuiteSpec(suite_id='dsh-skills', version=int(manifest.get('version', 1)), source=str(root), cases=tuple(cases))


def records(root: Path) -> list[Record]:
    root = Path(root).resolve()
    workflow = sha256((root / 'PROTOCOL.md').read_bytes()) if (root / 'PROTOCOL.md').is_file() else sha256('dsh-skills')
    suite = load_suite(root)
    case_map = {case.case_id: case for case in suite.cases}
    out = []
    result_paths = []
    seen = set()
    for directory in (root / 'results', root.parent / 'evaluation' / 'evidence'):
        if not directory.is_dir():
            continue
        for result_path in sorted(directory.glob('*/case-result.json')):
            if result_path.parent.name in seen:
                continue
            seen.add(result_path.parent.name)
            result_paths.append(result_path)
    for result_path in result_paths:
        try:
            raw = json.loads(result_path.read_text())
        except Exception:
            continue
        grade = raw.get('grade') or {}
        case_id = raw.get('case')
        case = case_map.get(case_id)
        if case is None:
            continue
        # Ignore stale trials that were produced by a different grader/prompt/truth.
        if raw.get('grader_sha256') and raw['grader_sha256'] != case.grader_sha256:
            continue
        if raw.get('prompt_sha256') and raw['prompt_sha256'] != case.prompt_sha256:
            continue
        if case.truth_sha256 and raw.get('truth_sha256') != case.truth_sha256:
            continue
        mode = raw.get('mode', 'unknown')
        score, maximum = grade.get('score'), grade.get('max')
        passed = bool(grade.get('passed')) if 'passed' in grade else (isinstance(score, int) and isinstance(maximum, int) and maximum > 0 and score == maximum)
        scored = isinstance(score, int) and isinstance(maximum, int) and maximum > 0 and not raw.get('fixture_changed')
        reward = 1.0 if passed else 0.0
        reward_max = 1.0
        error_text = str(grade.get('error') or '')
        if raw.get('incomplete'):
            outcome = 'incomplete'
        elif 'outer_devices' in error_text or 'RuntimeError' in error_text:
            outcome = 'infrastructure'
        elif scored:
            outcome = 'scored'
        else:
            outcome = 'failed'
        attempt = Attempt(
            attempt_id='a1', trial_id=result_path.parent.name, outcome=outcome,
            reward=reward if scored else None,
            max_reward=reward_max if scored else None,
            checks=grade.get('checks') or {},
            usage={k: int((raw.get('metrics') or {}).get('tokens', {}).get(k, 0) or 0)
                   for k in ('inputTokens', 'outputTokens', 'cacheReadTokens', 'cacheWriteTokens')},
            error=grade.get('error'),
        )
        manifest = RunManifest(
            run_id=f'ae-{result_path.parent.name}', suite='dsh-skills', case=case_id, arm=mode,
            workflow_sha256=workflow, prompt_sha256=raw.get('prompt_sha256') if isinstance(raw.get('prompt_sha256'), str) else case.prompt_sha256,
            skill_sha256=raw.get('skill_sha256') if isinstance(raw.get('skill_sha256'), str) else None,
            agent_runtime='dsh', model=raw.get('model') or 'unknown',
            provider='deepseek-official', source='agent_eval', split=raw.get('case_split') or case.split,
            scale=raw.get('case_scale') or case.scale,
            budgets={'max_tool_calls': raw.get('max_tool_calls')},
            environment={'sandbox_modes': raw.get('sandbox_modes') or [],
                         'case_sha256': raw.get('case_sha256'), 'grader_sha256': raw.get('grader_sha256'),
                         'truth_sha256': raw.get('truth_sha256'),
                         'fixture_sha256': raw.get('fixture_sha256'),
                         'baseline_skill_sha256': raw.get('baseline_skill_sha256')},
            evaluation={'trialId': result_path.parent.name, 'record': (result_path.relative_to(root) if result_path.is_relative_to(root) else Path('benchmarks/evaluation/evidence') / result_path.parent.name / 'case-result.json').as_posix()},
            started_at=raw.get('started_at') or '1970-01-01T00:00:00+00:00',
        )
        record = Record(record_id=manifest.run_id, manifest=manifest, state='sealed' if scored else 'failed',
                        attempts=(attempt,), metrics=summarize((attempt,)),
                        evidence={
                'result_sha256': tree_hash(result_path),
                'legacy': {'stack': 'agent_eval', 'path': (result_path.relative_to(root) if result_path.is_relative_to(root) else Path('benchmarks/evaluation/evidence') / result_path.parent.name / 'case-result.json').as_posix(),
                           'result_case_sha256': raw.get('case_sha256'),
                           'result_grader_sha256': raw.get('grader_sha256')},
                'limitations': ([x for x, bad in (
                    ('run grader hash differs from current case grader', raw.get('grader_sha256') not in (None, case.grader_sha256)),
                    ('run prompt hash missing; using current prompt hash', not isinstance(raw.get('prompt_sha256'), str)),
                    ('run case hash not compared to current source', False) ) if bad]),
            })
        out.append(record.with_hash())
    return out
