"""Host-authenticated Codex client with the verified Linux command sandbox."""

from functools import cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

from .base import Backend, PreparedTrial


MODEL = 'gpt-6.1-sol'
EFFORT = 'low'
COMMON_HEADER = ('If a skill is supplied under skill/, read skill/SKILL.md and only applicable supporting resources. '
                 'Named deliverables are exact workspace-relative paths; bare filenames belong at workspace root, '
                 'not under an added output/ directory.')


@cache
def legacy():
    """Reuse audited helpers without changing historical runner semantics."""
    path = Path(__file__).resolve().parents[5] / 'benchmarks/art_creation_ab/complex.py'
    loader = importlib.util.spec_from_file_location('skill_bench_legacy_complex', path)
    if loader is None or loader.loader is None:
        raise ValueError('The audited local sandbox helpers are unavailable.')
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def command(executable, package, workspace, renderer, final, attachments, thread=None, tools=None):
    args = legacy().command(executable, package, workspace, renderer, final, attachments, thread)
    if tools:
        from ..visual_runtime import config_args
        position = args.index('exec')
        args[position:position] = config_args(tools, package, renderer)
    return args


def normalize_usage(current, previous=None):
    result = legacy().feedback.turn_usage(current, previous)
    if result.get('usage_status') == 'nonmonotonic_thread_totals':
        raise ValueError('Thread cumulative usage must be monotonic.')
    if not all(type(result.get(key)) is int and result[key] >= 0 for key in ('input_tokens', 'cached_input_tokens', 'output_tokens', 'uncached_input_tokens')):
        raise ValueError('CLI usage is missing or inconsistent.')
    return result


def limits(spec):
    value = spec['limits']
    for key, ceiling in [('turn_seconds', 600), ('max_file_bytes', 8 * 1024 * 1024), ('max_workspace_bytes', 64 * 1024 * 1024)]:
        if type(value.get(key)) not in (int, float) or not 0 < value[key] <= ceiling:
            raise ValueError('Invalid execution ceiling: ' + key)
    return {'timeout_seconds': value['turn_seconds'], 'per_file_bytes': value['max_file_bytes'], 'workspace_bytes': value['max_workspace_bytes']}


def snapshot(workspace, destination, ceilings):
    bound = {'per_file_bytes': ceilings['max_file_bytes'], 'workspace_bytes': ceilings['max_workspace_bytes']}
    return legacy().capture(workspace, destination, bound)


def new_directory(path):
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('Private output/workspace directories cannot be symbolic links.')
    if any((parent / '.git').exists() for parent in (path, *path.parents)):
        raise ValueError('Runtime output and workspaces must stay outside repositories.')
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError('Existing nonempty output/workspaces cannot be retried or reused.')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path.resolve()


def regular_bytes(path, maximum):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError('Inputs must be regular, unlinked files.')
    if path.stat().st_size > maximum:
        raise ValueError('Input exceeds the per-file ceiling.')
    return path.read_bytes()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


class LocalCodexBackend(Backend):
    id = 'local_codex'
    capabilities = {'real_images': True, 'exact_resume': True, 'svg': True, 'png': True,
                    'private_snapshots': True, 'readonly_inputs': True,
                    'host_only_auth': True, 'command_network_disabled': True,
                    'browser_capture': True, 'playable_motion': True,
                    'action_trace_capture': True, 'web_audio_probe': True,
                    'blender': True, 'native_scene_reopen': True,
                    'continuous_playback': False, 'native_harbor': False}

    def fingerprint(self):
        base = Path(__file__).resolve().parents[5] / 'benchmarks/art_creation_ab'
        identities = {name: hashlib.sha256((base / name).read_bytes()).hexdigest() for name in ('run.py', 'feedback.py', 'complex.py')}
        identities['adapter'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        identities['codex_version'] = legacy().core.CLI_VERSION
        for name in ('visual_runtime.py', 'browser_driver.py', 'blender_driver.py', 'browser_client.py', 'browser_broker.py', 'browser_namespace.py', 'browser_resources.py', 'action_acceptance.py', 'observation_plans.py', 'failure_evidence.py'):
            path = Path(__file__).parent.parent / name
            identities[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        return hashlib.sha256(json.dumps(identities, sort_keys=True).encode()).hexdigest()

    def doctor(self, config):
        renderer = Path(config.get('renderer', legacy().DEFAULT_RENDERER)).resolve()
        report = legacy().core.doctor(renderer=renderer, readonly_inputs=True)
        tools = config.get('visual_tools', {})
        capabilities = dict(self.capabilities)
        for name in ('browser_capture', 'playable_motion', 'action_trace_capture', 'web_audio_probe', 'blender', 'native_scene_reopen'):
            capabilities[name] = False
        if tools:
            from ..visual_runtime import doctor, discover
            current = discover({name: tool['executable'] for name, tool in tools.items()},
                               ['browser_capture' if name == 'browser' else 'blender' for name in tools])
            if current != tools:
                raise ValueError('Visual runtime changed since the frozen experiment')
            visual = doctor(renderer, tools)
            report.update(visual=visual, passed=report['passed'] and visual['passed'])
            if visual['passed']:
                for name in ('browser_capture', 'playable_motion'):
                    capabilities[name] = 'browser' in tools
                for name in ('blender', 'native_scene_reopen'):
                    capabilities[name] = 'blender' in tools
                for name in ('action_trace_capture', 'web_audio_probe'):
                    capabilities[name] = visual.get('capability_checks', {}).get(name, {}).get('passed') is True
        missing = [name for name in config.get('required_capabilities', []) if not capabilities.get(name)]
        if missing:
            report.update(passed=False, missing_required_capabilities=missing)
        return {**report, 'backend': {'id': self.id, 'fingerprint': self.fingerprint()}, 'capabilities': capabilities}

    def prepare(self, spec, output):
        if spec.get('model') != MODEL or spec.get('effort') != EFFORT:
            raise ValueError('Model and effort must match the verified fixed configuration.')
        if spec.get('arm') not in {'none', 'previous', 'candidate'}:
            raise ValueError('Unknown experiment arm.')
        if bool(spec.get('skill_dir')) != (spec['arm'] != 'none'):
            raise ValueError('The none arm cannot receive a skill; other arms require a frozen skill.')
        ceilings = limits(spec)
        turns = spec['case']['turns']
        if not turns or len(turns) > 3 or len({turn['id'] for turn in turns}) != len(turns):
            raise ValueError('A trial supports one to three uniquely identified real turns.')
        if any(not isinstance(turn['id'], str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}', turn['id']) for turn in turns):
            raise ValueError('Invalid portable turn ID.')
        assets = {asset['id']: asset for asset in spec['case'].get('assets', [])}
        if len(assets) != len(spec['case'].get('assets', [])):
            raise ValueError('Duplicate asset IDs.')
        selected = {identifier for turn in turns for identifier in turn.get('attachments', [])}
        staged = {}
        for identifier in selected:
            if identifier not in assets or identifier not in spec.get('asset_paths', {}):
                raise ValueError('Attachment is not an explicitly supplied asset.')
            asset = assets[identifier]
            if asset.get('visibility') not in {'public', 'private'}:
                raise ValueError('Solver asset visibility must be public or private.')
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}', identifier):
                raise ValueError('Invalid portable asset ID.')
            source = Path(spec['asset_paths'][identifier])
            data = regular_bytes(source, ceilings['per_file_bytes'])
            if hashlib.sha256(data).hexdigest() != asset['sha256']:
                raise ValueError('Reference input hash differs from the frozen case.')
            legacy().image_format(data, source.suffix.lower())
            staged[identifier] = {'source': source, 'path': 'inputs/' + identifier + source.suffix.lower(), 'sha256': asset['sha256']}
        for turn in turns:
            if not isinstance(turn.get('prompt'), str) or not turn['prompt'].strip():
                raise ValueError('Each real turn needs a natural prompt.')
            for artifact in turn.get('artifacts', []):
                legacy().safe_path(artifact['path'])
        output = new_directory(output)
        workspace = new_directory(spec['workspace'])
        if workspace == output or output.is_relative_to(workspace):
            raise ValueError('Raw evaluator output cannot be inside the solver workspace.')
        (workspace / 'inputs').mkdir()
        skill_hash = None
        if spec.get('skill_dir'):
            files, identity = legacy().skill_files(directory=spec['skill_dir'])
            for name, data in files.items():
                if len(data) > ceilings['per_file_bytes']:
                    raise ValueError('Skill resource exceeds the per-file ceiling.')
                target = workspace / 'skill' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            skill_hash = identity['sha256']
        renderer = Path(spec['renderer']).resolve()
        from ..visual_runtime import discover, stage, environment
        tools = spec.get('backend_config', {}).get('visual_tools', {})
        required = spec['case'].get('capabilities', [])
        current = discover({name: tool['executable'] for name, tool in tools.items()}, required)
        if current and current != {name: tools.get(name) for name in current}:
            raise ValueError('Required visual tools must match frozen runtime identities')
        tools = current
        tool_hashes = stage(workspace, tools)
        base_environment = legacy().environment(renderer)
        if tools:
            base_environment = base_environment.replace('No browser playback or production avatar importer is configured.',
                                                         'No production avatar importer is configured.')
        prompts = [turn['prompt'] + '\n\n' + COMMON_HEADER + '\nDeliverable paths for this turn: '
                   + json.dumps([artifact['path'] for artifact in turn.get('artifacts', [])], ensure_ascii=False)
                   + '\nFrozen resource limits, including read-only inputs: '
                   + json.dumps(spec['limits'], sort_keys=True)
                   + '\n' + base_environment + environment(tools) for turn in turns]
        attachments = [[workspace / staged[identifier]['path'] for identifier in turn.get('attachments', [])] for turn in turns]
        prepared = PreparedTrial(spec, output, workspace, prompts, attachments, staged, skill_hash)
        prepared.state.update(visual_tools=tools, tool_hashes=tool_hashes)
        self.stage_turn(prepared, 0)
        if not legacy().inventory(workspace, ceilings)['passed']:
            raise ValueError('Initial workspace exceeds its declared ceilings.')
        if 'browser' in tools:
            from ..browser_broker import BrowserBroker
            prepared.state['browser_broker'] = BrowserBroker(workspace, tools)
        write_json(output / 'prepared.json', {'trial_id': spec['trial_id'], 'arm': spec['arm'], 'skill_hash': skill_hash,
                                            'prompt_sha256': [hashlib.sha256(p.encode()).hexdigest() for p in prompts],
                                            'assets': {key: {k: str(v) for k, v in val.items()} for key, val in staged.items()}})
        return prepared

    def stage_turn(self, prepared, index):
        for identifier in prepared.spec['case']['turns'][index].get('attachments', []):
            asset = prepared.assets[identifier]
            data = regular_bytes(asset['source'], prepared.spec['limits']['max_file_bytes'])
            if hashlib.sha256(data).hexdigest() != asset['sha256']:
                raise ValueError('Frozen input changed before its turn.')
            target = prepared.workspace / asset['path']
            if any(parent.is_symlink() for parent in (target, *target.parents)):
                raise ValueError('Input staging cannot follow symbolic links.')
            if target.exists():
                if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != asset['sha256']:
                    raise ValueError('A staged read-only input changed.')
            else:
                target.write_bytes(data)
            asset['staged'] = True

    def frozen_inputs(self, prepared):
        for asset in prepared.assets.values():
            path = prepared.workspace / asset['path']
            if asset.get('staged') and (not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']):
                raise ValueError('A staged read-only input changed.')
        if prepared.skill_hash:
            _, identity = legacy().skill_files(directory=prepared.workspace / 'skill')
            if identity['sha256'] != prepared.skill_hash:
                raise ValueError('Frozen read-only skill changed.')
        if prepared.state.get('tool_hashes'):
            root = prepared.workspace / 'tools'
            expected = prepared.state['tool_hashes']
            if root.is_symlink() or any(p.is_symlink() or not p.is_file() for p in root.iterdir()):
                raise ValueError('Frozen visual tools changed')
            actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
            if actual != expected:
                raise ValueError('Frozen visual tools changed')

    def execute(self, prepared, emit, through_turn=None):
        spec, output, workspace = prepared.spec, prepared.output, prepared.workspace
        result = prepared.state.setdefault('result', {'trial_id': spec['trial_id'], 'status': 'completed', 'turns': [],
                  'backend': {'id': self.id, 'fingerprint': self.fingerprint()}, 'failure_reason': None})
        if result['status'] != 'completed':
            return result
        identifier, previous_usage = None, None
        if result['turns']:
            identifier = result['turns'][-1]['thread_id']
            previous_usage = result['turns'][-1]['reported_cumulative_usage']
        active_row, active_phase, active_started = None, None, None
        try:
            preflight = self.doctor({'renderer': spec['renderer'], 'visual_tools': prepared.state.get('visual_tools', {})})
            if not preflight.get('passed'):
                raise ValueError('Sandbox preflight failed.')
            write_json(output / 'preflight.json', preflight)
            executable, package = legacy().core.runtime()
            renderer, ceilings = Path(spec['renderer']).resolve(), limits(spec)
            deadline = spec.get('backend_config', {}).get('run_deadline_epoch')
            for index, turn in enumerate(spec['case']['turns']):
                if index < len(result['turns']):
                    continue
                if through_turn is not None and index + 1 > through_turn:
                    break
                if deadline is not None and time.time() >= deadline:
                    raise ValueError('Experiment wall-clock deadline expired before call reservation.')
                self.stage_turn(prepared, index)
                self.frozen_inputs(prepared)
                if not legacy().inventory(workspace, ceilings)['passed']:
                    raise ValueError('Workspace ceiling exceeded before call reservation.')
                phase = output / ('turn-' + str(index + 1))
                phase.mkdir()
                # The caller owns the global budget and can reject this event.
                emit({'type': 'call_reserved', 'trial_id': spec['trial_id'], 'turn': index + 1, 'turn_id': turn['id']})
                emit({'type': 'turn_started', 'trial_id': spec['trial_id'], 'turn': index + 1, 'turn_id': turn['id']})
                started, status, process = time.monotonic(), 'completed', None
                active_phase, active_started = phase, started
                active_row = {'turn': index + 1, 'turn_id': turn['id'], 'status': 'failed', 'thread_id': identifier,
                              'usage': {}, 'reported_cumulative_usage': {}, 'seconds': 0, 'image_evidence': {},
                              'delivery': {'delivery_pass': False, 'quality_status': 'unassessed'}, 'artifacts': []}
                try:
                    with (phase / 'events.jsonl').open('w') as events, (phase / 'stderr.log').open('w') as error:
                        process = subprocess.Popen(command(executable, package, workspace, renderer, phase / 'final.txt', prepared.attachments[index], identifier,
                                                           tools=prepared.state.get('visual_tools')),
                                                   cwd=workspace, env=legacy().core.host_env(), stdin=subprocess.PIPE,
                                                   stdout=events, stderr=error, text=True, start_new_session=True)
                        first = True
                        while True:
                            remaining = ceilings['timeout_seconds'] - (time.monotonic() - started)
                            if deadline is not None:
                                remaining = min(remaining, deadline - time.time())
                            if remaining <= 0:
                                status = 'failed'; reason = 'turn timeout'; legacy().core.stop(process); break
                            try:
                                process.communicate(prepared.prompts[index] if first else None, timeout=min(1, remaining))
                                break
                            except subprocess.TimeoutExpired:
                                first = False
                                if prepared.state.get('browser_broker'):
                                    prepared.state['browser_broker'].service(started + ceilings['timeout_seconds'] if deadline is None else min(started + ceilings['timeout_seconds'], time.monotonic() + deadline - time.time()))
                                if not legacy().inventory(workspace, ceilings)['passed']:
                                    status = 'failed'; reason = 'workspace ceiling exceeded'; legacy().core.stop(process); break
                    if process.returncode and status == 'completed':
                        status, reason = 'failed', 'Codex client exited unsuccessfully'
                except BaseException:
                    if process is not None:
                        legacy().core.stop(process)
                    raise
                from ..failure_evidence import classify_cli_stream
                cli_evidence = classify_cli_stream(phase / 'events.jsonl')
                active_row.update(client_returncode=process.returncode, cli_event_evidence=cli_evidence)
                captured = snapshot(workspace, phase / 'artifacts', spec['limits'])
                active_row['capture'] = captured
                active_row['artifacts'] = [{'path': item['path'], 'sha256': item['sha256'], 'size': item['bytes'],
                                           'snapshot': (phase / 'artifacts' / item['path']).relative_to(output).as_posix()}
                                          for item in captured['artifacts'] if item.get('capture_status') == 'copied']
                if not captured['passed']:
                    active_row['capture_error'] = 'Workspace artifacts rejected by explicit size/link ceilings.'
                    if status == 'completed':
                        raise ValueError(active_row['capture_error'])
                self.frozen_inputs(prepared)
                if status != 'completed':
                    active_row['reported_cumulative_usage'] = {'usage_status': 'unavailable_for_failed_turn'}
                    if cli_evidence.get('stream_integrity') == 'valid':
                        try:
                            active_row['reported_cumulative_usage'] = legacy().core.usage(phase / 'events.jsonl')
                        except (OSError, ValueError, TypeError, AttributeError, RecursionError):
                            # Optional usage evidence cannot replace the execution failure.
                            pass
                    codes = cli_evidence.get('failure_codes', [])
                    if codes and reason == 'Codex client exited unsuccessfully':
                        reason += ' (' + ', '.join(codes) + ')'
                    raise ValueError(reason)
                current_thread = legacy().feedback.thread_id(phase / 'events.jsonl')
                uuid.UUID(current_thread)
                if identifier and current_thread != identifier:
                    raise ValueError('Exact resume returned a different thread UUID.')
                identifier = current_thread
                evidence = legacy().rollout_evidence(identifier, index + 1, workspace)
                if not evidence.get('rollout_found') or evidence['reference_input_image_items'] < len(prepared.attachments[index]):
                    raise ValueError('Actual user image / exact rollout evidence is missing.')
                raw = legacy().core.usage(phase / 'events.jsonl')
                if raw.get('usage_status') != 'reported_by_cli':
                    raise ValueError('CLI cumulative usage evidence is missing.')
                usage = normalize_usage(raw, previous_usage)
                previous_usage = raw
                from ..grading import grade_delivery
                delivery = grade_delivery(phase / 'artifacts', spec['case'], index + 1) if turn.get('artifacts') else legacy().artifact_checks(phase / 'artifacts', {'required_artifacts': []})
                row = {'turn': index + 1, 'turn_id': turn['id'], 'status': status, 'thread_id': identifier, 'usage': usage,
                       'client_returncode': process.returncode, 'cli_event_evidence': cli_evidence,
                       'reported_cumulative_usage': raw, 'seconds': time.monotonic() - started,
                       'image_evidence': evidence, 'delivery': delivery,
                       'artifacts': [{'path': item['path'], 'sha256': item['sha256'], 'size': item['bytes'],
                                      'snapshot': (phase / 'artifacts' / item['path']).relative_to(output).as_posix()}
                                     for item in captured['artifacts'] if item.get('capture_status') == 'copied']}
                write_json(phase / 'result.json', row)
                result['turns'].append(row)
                active_row = None
                emit({'type': 'turn_completed', 'trial_id': spec['trial_id'], 'turn': index + 1, 'turn_id': turn['id'], 'status': status})
                if status != 'completed':
                    raise ValueError(reason)
                if not delivery['delivery_pass']:
                    raise ValueError('Required artifact delivery failed; no automatic retry.')
        except KeyboardInterrupt:
            result.update(status='interrupted', failure_reason='Execution interrupted; no automatic retry.')
        except Exception as error:
            result.update(status='failed', failure_reason=str(error))
        if active_row is not None:
            active_row.update(status=result['status'], seconds=time.monotonic() - active_started, error=result['failure_reason'])
            if not (active_phase / 'artifacts').exists():
                active_row['capture'] = snapshot(workspace, active_phase / 'artifacts', spec['limits'])
                active_row['artifacts'] = [{'path': item['path'], 'sha256': item['sha256'], 'size': item['bytes'],
                                           'snapshot': (active_phase / 'artifacts' / item['path']).relative_to(output).as_posix()}
                                          for item in active_row['capture']['artifacts'] if item.get('capture_status') == 'copied']
            write_json(active_phase / 'result.json', active_row)
            result['turns'].append(active_row)
        write_json(output / 'backend-result.json', result)
        if prepared.state.get('browser_broker') and (through_turn is None or len(result['turns']) == len(spec['case']['turns']) or result['status'] != 'completed'):
            prepared.state['browser_broker'].close()
        return result

    def execute_trial(self, spec, output, emit):
        old_umask = os.umask(0o077)
        try:
            try:
                prepared = self.prepare(spec, output)
            except (OSError, ValueError, KeyError) as error:
                return {'trial_id': spec.get('trial_id'), 'status': 'failed', 'turns': [],
                        'backend': {'id': self.id, 'fingerprint': self.fingerprint()}, 'failure_reason': str(error)}
            return self.collect(prepared, self.execute(prepared, emit))
        finally:
            os.umask(old_umask)
