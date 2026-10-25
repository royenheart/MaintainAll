"""Bounded execution and independent mechanical regrading."""
import copy
import fcntl
import json
import os
import stat
import subprocess
import re
from pathlib import Path
import time

from .contracts import checked_file, content_hash, json_hash, validate_document
from .experiment import backend, load_experiment, renderer_identity
from .grading import grade_delivery
from .store import append_event, load_results, private_directory, read_events, state, write_immutable, write_projection


def seal_artifacts(root, result):
    for turn in result.get('turns', []):
        for item in turn.get('artifacts', []):
            data = checked_file(root, item['snapshot']).read_bytes()
            if len(data) != item['size'] or content_hash(data) != item['sha256']:
                raise ValueError('Snapshot inventory does not match captured artifact bytes')


def independently_grade(root, case, result):
    """Ignore solver quality assertions and backend format assertions."""
    result = copy.deepcopy(result)
    result['schema_version'] = 1
    numbers = [t.get('turn') for t in result.get('turns', [])]
    if numbers != list(range(1, len(numbers) + 1)) or len(numbers) > len(case['turns']):
        raise ValueError('Duplicate, skipped or unordered real-turn evidence')
    if any(t.get('turn_id', case['turns'][t['turn'] - 1]['id']) != case['turns'][t['turn'] - 1]['id'] for t in result.get('turns', [])):
        raise ValueError('Real-turn identifier differs from frozen case')
    if result['status'] == 'completed' and any(t.get('status') != 'completed' for t in result.get('turns', [])):
        result.update(status='failed', failure_reason='A failed turn cannot form a completed trial')
    seal_artifacts(root, result)
    for turn in result.get('turns', []):
        number = turn['turn']
        snapshot = Path(root) / f'turn-{number}/artifacts'
        turn['delivery'] = grade_delivery(snapshot, case, number)
        declared = {a['path']: a for a in case['turns'][number - 1]['artifacts']}
        for item in turn.get('artifacts', []):
            if item['path'] in declared:
                item.update({k: v for k, v in declared[item['path']].items() if k != 'path'})
        if not turn['delivery']['delivery_pass'] and result['status'] == 'completed':
            result.update(status='failed', failure_reason='Independent artifact delivery verification failed')
    if result['status'] == 'completed' and len(result.get('turns', [])) != len(case['turns']):
        result.update(status='failed', failure_reason='Incomplete real-turn evidence')
    result['quality_status'] = 'unassessed'
    validate_document(result, 'evidence')
    return result


def run_experiment(root, *, execute=False, adapter=None, budget_root=None, max_total_calls=69):
    """Run one frozen experiment once. Reservations are durable before launch."""
    root = Path(root).resolve()
    if not execute:
        return _run_experiment(root, adapter=adapter)
    try:
        descriptor = os.open(root / '.run.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError as error:
        raise ValueError('Experiment execution lock could not be opened safely') from error
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Experiment execution lock must be a regular, unlinked file')
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Experiment is already executing; concurrent launch is forbidden') from None
        return _run_experiment(root, execute=True, adapter=adapter, budget_root=budget_root,
                               max_total_calls=max_total_calls)
    finally:
        # Closing the descriptor releases the process lock even on failure.
        os.close(descriptor)


def _run_experiment(root, *, execute=False, adapter=None, budget_root=None, max_total_calls=69):
    """Execute only while the public entry point holds the experiment lock."""
    root = Path(root).resolve()
    manifest = load_experiment(root)
    if not execute:
        return state(root, manifest)
    if read_events(root) or load_results(root):
        raise ValueError('Experiment has already started; automatic retry is forbidden')
    execution = adapter or backend(manifest['backend'])
    if manifest.get('mode') != 'explicit_skill_provision':
        raise ValueError('Historical imports cannot be executed as fresh trials')
    current_verifier = json_hash({name: content_hash(Path(__file__).with_name(name).read_bytes()) for name in ('grading.py', 'runner.py')})
    if current_verifier != manifest['mechanical_verifier']['sha256']:
        raise ValueError('Mechanical verifier differs from the frozen experiment')
    if execution.fingerprint() != manifest['runtime']['adapter_sha256']:
        raise ValueError('Runtime adapter differs from the frozen experiment')
    if renderer_identity(manifest['runtime']['renderer']) != manifest['runtime']['renderer_identity']:
        raise ValueError('Renderer differs from the frozen experiment')
    doctor = execution.doctor({'renderer': manifest['runtime']['renderer'],
                               'visual_tools': manifest.get('backend_config', {}).get('visual_tools', {}),
                               'required_capabilities': sorted({v for c in manifest['cases'] for v in c['capabilities']})})
    write_immutable(root / 'doctor.json', doctor)
    if not doctor.get('passed'):
        raise ValueError('Execution doctor did not pass; no model was called')
    if budget_root is not None:
        if not 1 <= max_total_calls <= 69:
            raise ValueError('Global invocation ceiling exceeds the first-release budget')
        budget_root = private_directory(budget_root)
    append_event(root, {'type': 'run_started', 'manifest_sha256': content_hash((root / 'manifest.json').read_bytes())})
    deadline = time.time() + manifest['limits']['wall_seconds']
    cases = {c['id']: c for c in manifest['cases']}
    arms = {a['id']: a for a in manifest['arms']}
    reason = 'schedule_completed'
    try:
        for row in manifest['schedule']:
            if time.time() >= deadline:
                reason = 'wall_clock_budget_exhausted'
                break
            case, arm = cases[row['case_id']], arms[row['arm']]
            trial = root / 'trials' / row['trial_id']
            spec = {'trial_id': row['trial_id'], 'case': case, 'arm': row['arm'],
                    'skill_dir': str(root / arm['skill_snapshot']) if arm['skill_snapshot'] else None,
                    'asset_paths': {a['id']: str(root / a['path']) for a in case['assets']},
                    'workspace': str(root / 'workspaces' / row['trial_id']),
                    'model': manifest['model'], 'effort': manifest['effort'],
                    'renderer': manifest['runtime']['renderer'], 'limits': case['limits'],
                    'backend_config': {**manifest['backend_config'], 'run_deadline_epoch': deadline}}
            def emit(event):
                if event.get('trial_id') != row['trial_id']:
                    raise ValueError('Backend emitted an unknown trial')
                if event['type'] == 'call_reserved':
                    if type(event.get('turn')) is not int or not 1 <= event['turn'] <= len(case['turns']):
                        raise ValueError('Backend emitted an undeclared turn')
                    if time.time() >= deadline:
                        raise ValueError('Run wall-clock deadline expired before invocation')
                    if budget_root is not None:
                        append_event(budget_root, {**event, 'trial_id': manifest['id'] + '/' + row['trial_id']}, max_total_calls)
                append_event(root, event, manifest['limits']['max_calls'])
            try:
                result = execution.execute_trial(spec, trial, emit)
                if result.get('trial_id') != row['trial_id']:
                    raise ValueError('Backend result identifies a different trial')
                result = independently_grade(trial, case, result)
            except KeyboardInterrupt:
                reason = 'interrupted'
                break
            except Exception as error:
                result = {'schema_version': 1, 'trial_id': row['trial_id'], 'status': 'failed',
                          'turns': [], 'failure_reason': str(error), 'quality_status': 'unassessed'}
            sha = write_immutable(trial / 'result.json', result)
            write_immutable(trial / 'result-seal.json', {'sha256': sha})
            append_event(root, {'type': 'trial_completed', 'trial_id': row['trial_id'],
                                'status': result['status'], 'result_sha256': sha})
            write_projection(root / 'state.json', state(root, manifest))
            if result['status'] == 'interrupted':
                reason = 'interrupted'
                break
    finally:
        append_event(root, {'type': 'run_finished', 'reason': reason})
        write_projection(root / 'state.json', state(root, manifest))
    return state(root, manifest)


def regrade(root, *, reopen_sources=False):
    """Append a new verifier version without re-running generation."""
    root = Path(root).resolve()
    manifest = load_experiment(root)
    cases = {c['id']: c for c in manifest['cases']}
    schedules = {r['trial_id']: r for r in manifest['schedule']}
    results = []
    revision = len(list((root / 'regrades').glob('*.json'))) + 1
    if reopen_sources and renderer_identity(manifest['runtime']['renderer']) != manifest['runtime'].get('renderer_identity') and manifest['mode'] != 'legacy_import':
        raise ValueError('Renderer changed since the frozen source evidence')
    current_source_tools = {}
    if reopen_sources:
        from .visual_runtime import regrade_tools
        frozen_tools = manifest.get('backend_config', {}).get('visual_tools', {})
        required = (['browser_capture'] if 'browser' in frozen_tools else []) + (['blender'] if 'blender' in frozen_tools else [])
        current_source_tools = regrade_tools(frozen_tools, required)
    for recorded in load_results(root):
        trial = root / 'trials' / recorded['trial_id']
        seal = json.loads(checked_file(trial, 'result-seal.json').read_text())
        if content_hash(checked_file(trial, 'result.json').read_bytes()) != seal['sha256']:
            raise ValueError('Immutable result seal mismatch')
        graded = independently_grade(trial, cases[schedules[recorded['trial_id']]['case_id']], recorded)
        if reopen_sources:
            from .verifier import reopen_svg, reopen_visual, reference_assets
            for turn in graded['turns']:
                evidence = []
                for item in turn['artifacts']:
                    if item.get('kind') != 'editable' or item.get('format') not in {'svg', 'html', 'blend'}:
                        continue
                    target = root / 'verifier-workspaces' / str(revision) / recorded['trial_id'] / str(turn['turn']) / item['sha256']
                    try:
                        if item['format'] == 'svg':
                            evidence.append(reopen_svg(root, recorded['trial_id'], item, manifest['runtime']['renderer'], target))
                        else:
                            row = schedules[recorded['trial_id']]
                            case = cases[row['case_id']]
                            from .observation_plans import plan_for_turn
                            observation = plan_for_turn(case, turn['turn'])
                            if observation and observation['source_artifact'] != item['path']:
                                observation = None
                            evidence.append(reopen_visual(root, recorded['trial_id'], item, manifest['runtime']['renderer'], target,
                                                          current_source_tools, siblings=turn['artifacts'], assets=reference_assets(case, turn['turn']),
                                                          browser_scenario=manifest.get('backend_config', {}).get('browser_capture_scenario'),
                                                          browser_plan=observation))
                    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                        evidence.append({'source_sha256': item['sha256'], 'source_reopen_verified': False,
                                         'source_editability_verified': False, 'reason': str(error), 'quality_status': 'unassessed'})
                turn['source_verification'] = evidence
                turn['source_editability_verified'] = bool(evidence) and all(e['source_editability_verified'] for e in evidence)
        results.append(graded)
    verifier = json_hash({name: content_hash(Path(__file__).with_name(name).read_bytes()) for name in ('grading.py', 'runner.py')})
    source_runtime = None
    if reopen_sources:
        from .backends.local_codex import LocalCodexBackend
        source_runtime = json_hash({'renderer': renderer_identity(manifest['runtime']['renderer']),
                                   'sandbox_adapter': LocalCodexBackend().fingerprint(),
                                   'visual_tools': current_source_tools,
                                   'browser_capture_scenario': manifest.get('backend_config', {}).get('browser_capture_scenario')})
    from .verifier import verifier_identity
    value = {'schema_version': 1, 'verifier_sha256': verifier, 'generation_calls': 0, 'reopen_sources': reopen_sources,
             'source_runtime_fingerprint': source_runtime,
             'source_verifier_sha256': verifier_identity() if reopen_sources else None,
             'manifest_sha256': content_hash((root / 'manifest.json').read_bytes()),
             'source_result_hashes': {r['trial_id']: content_hash((root / 'trials' / r['trial_id'] / 'result.json').read_bytes()) for r in load_results(root)},
             'results': results, 'quality_status': 'unassessed'}
    value['id'] = json_hash(value)
    sha = write_immutable(root / 'regrades' / (value['id'] + '.json'), value)
    if not any(e.get('type') == 'regrade_frozen' and e.get('id') == value['id'] for e in read_events(root)):
        append_event(root, {'type': 'regrade_frozen', 'id': value['id'], 'record_sha256': sha})
    return value


def load_regrade(root, path):
    """Accept only an unchanged verifier record bound to this frozen run."""
    root, path = Path(root).resolve(), Path(path).absolute()
    if not path.is_relative_to(root / 'regrades'):
        raise ValueError('Regrade must come from this run regrades directory')
    value = json.loads(checked_file(root, path.relative_to(root).as_posix()).read_text())
    if value.get('id') != json_hash({k: v for k, v in value.items() if k != 'id'}) or path.stem != value['id']:
        raise ValueError('Regrade content fingerprint mismatch')
    if type(value.get('schema_version')) is not int or value['schema_version'] != 1:
        raise ValueError('Unsupported regrade schema version')
    if type(value.get('generation_calls')) is not int or value['generation_calls'] != 0:
        raise ValueError('Mechanical regrading must retain zero generation calls')
    if type(value.get('reopen_sources')) is not bool or value.get('quality_status') != 'unassessed':
        raise ValueError('Regrade scope or quality status is invalid')
    for key in ('source_runtime_fingerprint', 'source_verifier_sha256'):
        identity = value.get(key)
        if value['reopen_sources']:
            if not isinstance(identity, str) or not re.fullmatch(r'[0-9a-f]{64}', identity):
                raise ValueError('Reopened source evidence requires a valid source identity')
        elif identity is not None:
            raise ValueError('A no-reopen record cannot claim a source identity')
    record_sha = content_hash(path.read_bytes())
    if not any(e.get('type') == 'regrade_frozen' and e.get('id') == value['id'] and e.get('record_sha256') == record_sha for e in read_events(root)):
        raise ValueError('Regrade has no matching trusted verifier event')
    if value['manifest_sha256'] != content_hash(checked_file(root, 'manifest.json').read_bytes()):
        raise ValueError('Regrade belongs to a different frozen manifest')
    actual = {r['trial_id']: content_hash(checked_file(root, 'trials/' + r['trial_id'] + '/result.json').read_bytes()) for r in load_results(root)}
    if value['source_result_hashes'] != actual:
        raise ValueError('Regrade generation evidence changed')
    if not re.fullmatch(r'[0-9a-f]{64}', value.get('verifier_sha256', '')):
        raise ValueError('Regrade verifier identity is invalid')
    for result in value['results']:
        if result.get('quality_status') != 'unassessed' or value.get('quality_status') != 'unassessed':
            raise ValueError('Mechanical regrading cannot claim an independent quality review')
        validate_document(result, 'evidence')
        seal_artifacts(root / 'trials' / result['trial_id'], result)
        original = next((r for r in load_results(root) if r['trial_id'] == result['trial_id']), None)
        if original is None:
            raise ValueError('Regrade contains an undeclared trial')
        def generation_fields(record):
            mutable_turn = {'delivery', 'source_verification', 'source_editability_verified'}
            rows = []
            for turn in record['turns']:
                row = {k: v for k, v in turn.items() if k not in mutable_turn and k != 'artifacts'}
                row['artifacts'] = [{k: a[k] for k in ('path', 'snapshot', 'sha256', 'size')} for a in turn['artifacts']]
                rows.append(row)
            return {'trial_id': record['trial_id'], 'backend': record.get('backend'), 'turns': rows}
        if generation_fields(result) != generation_fields(original):
            raise ValueError('Regrade changed immutable generation telemetry or real-turn evidence')
        if result['status'] != original['status'] and not (original['status'] == 'completed' and result['status'] == 'failed' and any(not t['delivery']['delivery_pass'] for t in result['turns'])):
            raise ValueError('Regrade changed generation status without a failed delivery check')
        manifest = load_experiment(root)
        row = next(r for r in manifest['schedule'] if r['trial_id'] == result['trial_id'])
        case = next(c for c in manifest['cases'] if c['id'] == row['case_id'])
        for turn in result['turns']:
            if not value['reopen_sources'] and turn.get('source_verification'):
                raise ValueError('A no-reopen record cannot claim source verification')
            declared = {a['path']: a for a in case['turns'][turn['turn'] - 1]['artifacts']}
            for item in turn['artifacts']:
                expected = declared.get(item['path'], next((a for t in original['turns'] if t['turn'] == turn['turn'] for a in t['artifacts'] if a['path'] == item['path']), {}))
                if any(item.get(k) != expected.get(k) for k in ('kind', 'format', 'width', 'height')):
                    raise ValueError('Regrade changed frozen artifact purpose or format')
            for proof in turn.get('source_verification', []):
                sources = {a['sha256']: a.get('format') for a in turn['artifacts'] if a.get('kind') == 'editable' and a.get('format') in {'svg', 'html', 'blend'}}
                if proof.get('source_sha256') not in sources:
                    raise ValueError('Source reopen proof does not refer to a declared supported source')
                if proof.get('source_reopen_verified'):
                    html = sources[proof['source_sha256']] == 'html'
                    scope_ok = proof.get('generated_code_executed') is True and proof.get('execution_scope') == 'sandboxed-html' if html else proof.get('generated_code_executed') is False
                    if proof.get('verifier_sha256') != value['source_verifier_sha256'] or proof.get('quality_status') != 'unassessed' or not scope_ok:
                        raise ValueError('Source reopen verifier identity or scope is invalid')
                    for artifact in proof['rendered'].values():
                        data = checked_file(root, artifact['path']).read_bytes()
                        if content_hash(data) != artifact['sha256'] or len(data) != artifact['size']:
                            raise ValueError('Source rebuild image differs from its evidence inventory')
                        from .grading import _png
                        _png(data)
                    if proof.get('trace'):
                        trace = proof['trace']
                        data = checked_file(root, trace['path']).read_bytes()
                        if len(data) > 8 * 1024 * 1024 or content_hash(data) != trace['sha256'] or len(data) != trace['size']:
                            raise ValueError('Visual proof trace differs from its evidence inventory')
                        json.loads(data)
                    if html and proof.get('source_editability_verified'):
                        raise ValueError('Browser playback cannot certify native source editability')
                    if sources[proof['source_sha256']] == 'blend' and proof.get('source_editability_verified'):
                        native = proof.get('modified_native', {})
                        if not native.get('independent_reopen_verified') or not native.get('edit_observed') or not native.get('raster_pixels_changed'):
                            raise ValueError('Native edit proof lacks independent reopen and observed changed pixels')
                        data = checked_file(root, native['path']).read_bytes()
                        if len(data) > 8 * 1024 * 1024 or content_hash(data) != native['sha256'] or len(data) != native['size']:
                            raise ValueError('Modified native source differs from its evidence inventory')
                    if proof.get('source_editability_verified') and (not proof.get('edit') or proof['rendered']['source']['sha256'] == proof['rendered']['edited']['sha256']):
                        raise ValueError('Source fill-edit claim has no distinct rebuilt pixels')
            claims = turn.get('source_verification', [])
            if turn.get('source_editability_verified') is True and (not claims or not all(c.get('source_reopen_verified') and c.get('source_editability_verified') for c in claims)):
                raise ValueError('Source editability lacks verified bounded reopen evidence')
    if {r['trial_id'] for r in value['results']} != set(actual) or len(value['results']) != len(actual):
        raise ValueError('Regrade trial population differs from generation evidence')
    return value
