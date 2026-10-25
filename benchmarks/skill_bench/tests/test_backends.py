"""Offline backend contracts and security regressions; never call a model."""

import hashlib
import asyncio
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))


def module(test, name='local_codex'):
    path = SRC / 'skill_bench' / 'backends' / (name + '.py')
    test.assertTrue(path.is_file(), 'The thin backend implementation is missing.')
    return importlib.import_module('skill_bench.backends.' + name)


def fixture(root, arm='candidate'):
    image = b'\xff\xd8\xfffixture\xff\xd9'
    (root / 'reference.jpg').write_bytes(image)
    (root / 'skill-source').mkdir()
    (root / 'skill-source/SKILL.md').write_text('# Test skill\n')
    case = {'id': 'test', 'assets': [{'id': 'ref', 'path': 'ref.jpg', 'sha256': hashlib.sha256(image).hexdigest(), 'license': 'CC0', 'source': 'Synthetic test', 'visibility': 'public'}], 'atoms': [{'criterion': 'SECRET_REVIEW_RUBRIC'}], 'requirements': [{'text': 'SECRET_REVIEW_REQUIREMENT'}], 'turns': [{'id': 't1', 'prompt': 'Make two directions.', 'attachments': ['ref'], 'artifacts': []}, {'id': 't2', 'prompt': 'Keep B and adjust A.', 'attachments': [], 'artifacts': []}]}
    return {'trial_id': 'test-trial', 'case': case, 'arm': arm, 'skill_dir': str(root / 'skill-source') if arm != 'none' else None, 'asset_paths': {'ref': str(root / 'reference.jpg')}, 'workspace': str(root / 'workspace'), 'model': 'gpt-6.1-sol', 'effort': 'low', 'renderer': str(root / 'renderer'), 'limits': {'turn_seconds': 5, 'max_file_bytes': 8388608, 'max_workspace_bytes': 33554432}, 'backend_config': {}}


class BackendTests(unittest.TestCase):
    def test_actual_images_and_exact_resume_do_not_upload_credentials(self):
        m = module(self)
        with mock.patch.object(m.legacy().core, 'host_skill_paths', return_value=[]):
            args = m.command('codex', Path('/runtime/codex'), Path('/workspace'), Path('/renderer'), Path('/private/final'), [Path('/workspace/inputs/ref.jpg')], '12345678-1234-1234-1234-123456789abc')
        self.assertIn('--image', args)
        self.assertEqual(args[-3:], ['--', '12345678-1234-1234-1234-123456789abc', '-'])
        self.assertNotIn('--last', args)
        self.assertNotIn('--ephemeral', args)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', args)
        self.assertTrue(any('inputs' in arg and 'read' in arg for arg in args))

    def test_prepare_stages_only_selected_inputs_and_never_rubrics(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root)
            prepared = m.LocalCodexBackend().prepare(spec, root / 'output')
            self.assertEqual((root / 'workspace/inputs/ref.jpg').read_bytes(), (root / 'reference.jpg').read_bytes())
            self.assertFalse(any('SECRET_REVIEW' in p.read_text(errors='ignore') for p in (root / 'workspace').rglob('*') if p.is_file()))
            self.assertNotIn('SECRET_REVIEW', prepared.prompts[0])
            self.assertTrue((root / 'workspace/skill/SKILL.md').is_file())
            self.assertEqual(prepared.attachments[1], [])

    def test_public_deliverable_paths_are_exact_current_turn_and_identical_for_all_arms(self):
        m = module(self); prompts = []
        with tempfile.TemporaryDirectory() as tmp:
            for arm in ('none', 'previous', 'candidate'):
                root = Path(tmp) / arm; root.mkdir(); spec = fixture(root, arm)
                spec['renderer'] = '/same/renderer-runtime'
                spec['case']['turns'][0]['artifacts'] = [{'path': 'a.svg', 'kind': 'editable', 'format': 'svg'}]
                spec['case']['turns'][1]['artifacts'] = [{'path': 'nested/b.svg', 'kind': 'editable', 'format': 'svg'}]
                prepared = m.LocalCodexBackend().prepare(spec, root / 'output')
                prompts.append(prepared.prompts)
        self.assertEqual(prompts[0], prompts[1]); self.assertEqual(prompts[1], prompts[2])
        self.assertIn('Named deliverables are exact workspace-relative paths', prompts[0][0])
        self.assertIn('bare filenames belong at workspace root', prompts[0][0])
        self.assertIn('a.svg', prompts[0][0]); self.assertNotIn('nested/b.svg', prompts[0][0])
        self.assertIn('nested/b.svg', prompts[0][1]); self.assertNotIn('a.svg', prompts[0][1])
        self.assertFalse(any('SECRET_REVIEW' in prompt for prompt in prompts[0]))

    def test_none_arm_contains_no_skill_and_hidden_assets_fail_closed(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root, 'none')
            prepared = m.LocalCodexBackend().prepare(spec, root / 'output')
            self.assertFalse((root / 'workspace/skill').exists())
            self.assertNotIn('Read skill/SKILL.md', prepared.prompts[0])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root)
            spec['case']['assets'][0]['visibility'] = 'evaluator'
            with self.assertRaisesRegex(ValueError, 'visibility'):
                m.LocalCodexBackend().prepare(spec, root / 'output')

    def test_asset_hash_and_workspace_escape_fail_before_model_reservation(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root)
            spec['case']['assets'][0]['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'hash'):
                m.LocalCodexBackend().prepare(spec, root / 'output')

    def test_later_input_staging_cannot_follow_a_replaced_input_directory(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root); spec['case']['turns'][0]['attachments'] = []
            spec['case']['turns'][1]['attachments'] = ['ref']
            backend = m.LocalCodexBackend(); prepared = backend.prepare(spec, root / 'output')
            outside = root / 'outside'; outside.mkdir()
            (prepared.workspace / 'inputs').rmdir()
            (prepared.workspace / 'inputs').symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symbolic'):
                backend.stage_turn(prepared, 1)
            self.assertFalse((outside / 'ref.jpg').exists())

    def test_turn_ids_cannot_escape_native_step_directories(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root)
            spec['case']['turns'][0]['id'] = '../outside'
            with self.assertRaisesRegex(ValueError, 'turn ID'):
                m.LocalCodexBackend().prepare(spec, root / 'output')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root)
            spec['case']['turns'][0]['artifacts'] = [{'path': '../auth.json', 'kind': 'source', 'format': 'json'}]
            with self.assertRaises(ValueError):
                m.LocalCodexBackend().prepare(spec, root / 'output')

    def test_usage_is_a_delta_and_nonmonotonic_totals_fail(self):
        m = module(self)
        old = {'input_tokens': 100, 'cached_input_tokens': 70, 'output_tokens': 10}
        new = {'input_tokens': 180, 'cached_input_tokens': 140, 'output_tokens': 20}
        usage = m.normalize_usage(new, old)
        self.assertEqual(usage['input_tokens'], 80)
        self.assertEqual(usage['uncached_input_tokens'], 10)
        self.assertEqual(usage['output_tokens'], 10)
        with self.assertRaisesRegex(ValueError, 'monotonic'):
            m.normalize_usage(old, new)

    def test_oversize_and_symlink_artifacts_are_explicit_failures(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'too-large.svg').write_bytes(b'x' * 1025)
            result = m.snapshot(root, root / 'snapshot', {'max_file_bytes': 1024, 'max_workspace_bytes': 2048})
            self.assertFalse(result['passed'])
            self.assertEqual(result['artifacts'][0]['capture_status'], 'rejected_due_to_workspace_violation')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'link').symlink_to('/etc/passwd')
            result = m.snapshot(root, root / 'snapshot', {'max_file_bytes': 1024, 'max_workspace_bytes': 2048})
            self.assertFalse(result['passed'])

    def test_call_budget_rejection_occurs_before_process_launch(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root)
            backend = m.LocalCodexBackend()
            def emit(event):
                if event['type'] == 'call_reserved':
                    raise RuntimeError('global budget denied')
            with mock.patch.object(backend, 'doctor', return_value={'passed': True}), mock.patch.object(m.legacy().core, 'runtime', return_value=('codex', Path('/runtime/codex'))), mock.patch.object(m.subprocess, 'Popen') as launch:
                result = backend.execute_trial(spec, root / 'output', emit)
            self.assertEqual(result['status'], 'failed')
            self.assertIn('budget denied', result['failure_reason'])
            launch.assert_not_called()

    def test_harbor_never_claims_native_when_runtime_is_unavailable(self):
        m = module(self, 'harbor')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root)
            spec['backend_config']['harbor_runtime'] = str(root / 'missing-runtime')
            events = []
            result = m.HarborBackend().execute_trial(spec, root / 'output', events.append)
            self.assertEqual(result['status'], 'unsupported')
            self.assertFalse(any(event['type'] == 'call_reserved' for event in events))
            self.assertEqual(result['backend']['id'], 'harbor')

    def test_real_turn_sequence_uses_integer_events_and_cumulative_deltas(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root); events = []; commands = []
            identifier = '12345678-1234-1234-1234-123456789abc'
            class Process:
                returncode = 0
                def __init__(self, args, **kwargs):
                    commands.append(args); n = len(commands)
                    kwargs['stdout'].write(json.dumps({'type': 'thread.started', 'thread_id': identifier}) + '\n')
                    kwargs['stdout'].write(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': n * 100, 'cached_input_tokens': n * 70, 'output_tokens': n * 10}}) + '\n')
                def communicate(self, prompt, timeout):
                    (root / 'workspace/notes.md').write_text('An actual prose handoff.')
            backend = m.LocalCodexBackend()
            evidence = {'rollout_found': True, 'reference_input_image_items': 1, 'image_items': 1}
            with mock.patch.object(backend, 'doctor', return_value={'passed': True}), mock.patch.object(m.legacy().core, 'runtime', return_value=('codex', Path('/runtime/codex'))), mock.patch.object(m.legacy().core, 'host_skill_paths', return_value=[]), mock.patch.object(m.legacy(), 'rollout_evidence', return_value=evidence), mock.patch.object(m.subprocess, 'Popen', Process):
                result = backend.execute_trial(spec, root / 'output', events.append)
            self.assertEqual(result['status'], 'completed', result['failure_reason'])
            self.assertEqual([r['turn'] for r in result['turns']], [1, 2])
            self.assertEqual([r['turn_id'] for r in result['turns']], ['t1', 't2'])
            self.assertEqual([e['turn'] for e in events if e['type'] == 'call_reserved'], [1, 2])
            self.assertEqual(result['turns'][1]['usage']['input_tokens'], 100)
            self.assertEqual(commands[1][-3:], ['--', identifier, '-'])
            self.assertEqual(result['turns'][1]['artifacts'][0]['snapshot'], 'turn-2/artifacts/notes.md')
            self.assertTrue((root / 'output/backend-result.json').is_file())
            self.assertFalse((root / 'output/result.json').exists())

    def test_expired_experiment_does_not_reserve_or_launch_model(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root); events = []
            spec['backend_config']['run_deadline_epoch'] = time.time() - 1
            backend = m.LocalCodexBackend()
            with mock.patch.object(backend, 'doctor', return_value={'passed': True}), mock.patch.object(m.legacy().core, 'runtime', return_value=('codex', Path('/runtime/codex'))), mock.patch.object(m.subprocess, 'Popen') as launch:
                result = backend.execute_trial(spec, root / 'output', events.append)
            self.assertIn(result['status'], ['failed', 'interrupted'])
            self.assertFalse(any(e['type'] == 'call_reserved' for e in events))
            launch.assert_not_called()

    def test_failed_client_preserves_a_failed_turn_and_does_not_retry(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root); launched = []
            class Process:
                returncode = 7
                def __init__(self, args, **kwargs):
                    launched.append(args)
                    kwargs['stdout'].write('{"type":"error","message":"offline failure fixture"}\n')
                def communicate(self, prompt, timeout):
                    (root / 'workspace/notes.md').write_text('Partial work before the client failed.')
            backend = m.LocalCodexBackend()
            with mock.patch.object(backend, 'doctor', return_value={'passed': True}), mock.patch.object(m.legacy().core, 'runtime', return_value=('codex', Path('/runtime/codex'))), mock.patch.object(m.legacy().core, 'host_skill_paths', return_value=[]), mock.patch.object(m.subprocess, 'Popen', Process):
                result = backend.execute_trial(spec, root / 'output', lambda event: None)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(len(launched), 1)
            self.assertEqual(len(result['turns']), 1)
            self.assertEqual(result['turns'][0]['status'], 'failed')
            self.assertTrue((root / 'output/turn-1/events.jsonl').is_file())
            self.assertTrue((root / 'output/turn-1/artifacts/notes.md').is_file())

    def test_route_discovery_failure_is_not_masked_by_missing_usage(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root); launched = []
            class Process:
                returncode = 7
                def __init__(self, args, **kwargs):
                    launched.append(args)
                    for event in [{'type': 'thread.started', 'thread_id': '12345678-1234-1234-1234-123456789abc'},
                                  {'type': 'turn.started'}, {'type': 'error', 'message': 'workspace routing discovery failed'},
                                  {'type': 'turn.failed', 'error': {'message': 'workspace routing discovery failed'}}]:
                        kwargs['stdout'].write(json.dumps(event) + '\n')
                def communicate(self, prompt, timeout):
                    pass
            backend = m.LocalCodexBackend()
            with mock.patch.object(backend, 'doctor', return_value={'passed': True}), mock.patch.object(m.legacy().core, 'runtime', return_value=('codex', Path('/runtime/codex'))), mock.patch.object(m.legacy().core, 'host_skill_paths', return_value=[]), mock.patch.object(m.subprocess, 'Popen', Process):
                result = backend.execute_trial(spec, root / 'output', lambda event: None)
            self.assertEqual(result['failure_reason'], 'Codex client exited unsuccessfully (route-discovery)')
            self.assertEqual(len(launched), 1)
            row = result['turns'][0]
            self.assertEqual(row['client_returncode'], 7)
            self.assertEqual(row['cli_event_evidence']['model_output'], 'absent')
            self.assertEqual(row['cli_event_evidence']['failure_codes'], ['route-discovery'])
            self.assertEqual(row['usage'], {})

    def test_timeout_keeps_partial_output_and_original_failure_reason(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root); spec['limits']['turn_seconds'] = 0.01
            launched = []
            class Process:
                returncode = None
                def __init__(self, args, **kwargs):
                    launched.append(args)
                    kwargs['stdout'].write(json.dumps({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'A partial design.'}}) + '\n')
                def communicate(self, prompt, timeout):
                    (root / 'workspace/notes.md').write_text('Partial work.')
                    time.sleep(0.02)
                    raise m.subprocess.TimeoutExpired('fixture', timeout)
            backend = m.LocalCodexBackend()
            with mock.patch.object(backend, 'doctor', return_value={'passed': True}), mock.patch.object(m.legacy().core, 'runtime', return_value=('codex', Path('/runtime/codex'))), mock.patch.object(m.legacy().core, 'host_skill_paths', return_value=[]), mock.patch.object(m.legacy().core, 'stop'), mock.patch.object(m.subprocess, 'Popen', Process):
                result = backend.execute_trial(spec, root / 'output', lambda event: None)
            self.assertEqual(result['failure_reason'], 'turn timeout')
            self.assertEqual(len(launched), 1)
            self.assertEqual(result['turns'][0]['cli_event_evidence']['model_output'], 'observed')
            self.assertTrue((root / 'output/turn-1/artifacts/notes.md').is_file())

    def test_failed_malformed_stream_cannot_mask_client_exit_or_prove_absence(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root)
            class Process:
                returncode = 9
                def __init__(self, args, **kwargs):
                    kwargs['stdout'].write('[]\n')
                def communicate(self, prompt, timeout):
                    pass
            backend = m.LocalCodexBackend()
            with mock.patch.object(backend, 'doctor', return_value={'passed': True}), mock.patch.object(m.legacy().core, 'runtime', return_value=('codex', Path('/runtime/codex'))), mock.patch.object(m.legacy().core, 'host_skill_paths', return_value=[]), mock.patch.object(m.subprocess, 'Popen', Process):
                result = backend.execute_trial(spec, root / 'output', lambda event: None)
            self.assertEqual(result['failure_reason'], 'Codex client exited unsuccessfully')
            self.assertEqual(result['turns'][0]['cli_event_evidence']['model_output'], 'unknown')

    def test_capture_rejection_is_separate_from_an_already_failed_client(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root); spec['limits']['max_file_bytes'] = 4096
            class Process:
                returncode = 7
                def __init__(self, args, **kwargs):
                    kwargs['stdout'].write('{"type":"error","message":"workspace routing discovery failed"}\n')
                def communicate(self, prompt, timeout):
                    (root / 'workspace/notes.md').write_bytes(b'x' * 4097)
            backend = m.LocalCodexBackend()
            with mock.patch.object(backend, 'doctor', return_value={'passed': True}), mock.patch.object(m.legacy().core, 'runtime', return_value=('codex', Path('/runtime/codex'))), mock.patch.object(m.legacy().core, 'host_skill_paths', return_value=[]), mock.patch.object(m.subprocess, 'Popen', Process):
                result = backend.execute_trial(spec, root / 'output', lambda event: None)
            self.assertEqual(result['failure_reason'], 'Codex client exited unsuccessfully (route-discovery)')
            self.assertFalse(result['turns'][0]['capture']['passed'])
            self.assertIn('size/link ceilings', result['turns'][0]['capture_error'])
            self.assertFalse((root / 'output/turn-1/artifacts/notes.md').exists())

    def test_harbor_source_pin_rejects_lookalike_archive_urls(self):
        m = module(self, 'harbor')
        distribution = mock.Mock(version=m.VERSION)
        distribution.read_text.return_value = json.dumps({'url': 'https://untrusted.invalid/' + m.SOURCE_SHA + '.tar.gz'})
        with mock.patch.object(m.importlib.metadata, 'distribution', return_value=distribution):
            with self.assertRaisesRegex(ValueError, 'provenance'):
                m.runtime_check({})

    def test_harbor_local_source_checks_installed_bytes_against_git_objects(self):
        m = module(self, 'harbor')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); installed = root / 'harbor/example.py'
            installed.parent.mkdir(); original = b'VALUE = 1\n'; installed.write_bytes(original)
            blob = hashlib.sha1(b'blob ' + str(len(original)).encode() + b'\0' + original).hexdigest()
            tree = b'100644 blob ' + blob.encode() + b'\tsrc/harbor/example.py\0'
            distribution = mock.Mock(files=[Path('harbor/example.py')])
            distribution.locate_file.side_effect = lambda relative: root / relative
            def output(args, **kwargs):
                if 'get-url' in args:
                    return 'https://github.com/harbor-framework/harbor.git\n'
                if 'rev-parse' in args:
                    return m.SOURCE_SHA + '\n'
                return tree
            with mock.patch.object(m.subprocess, 'check_output', side_effect=output):
                proof = m.verify_local_git_source(distribution, root.as_uri())
                self.assertEqual(proof['verified_package_files'], 1)
                installed.write_bytes(b'VALUE = 2\n')
                with self.assertRaisesRegex(ValueError, 'bytes differ'):
                    m.verify_local_git_source(distribution, root.as_uri())

    def test_harbor_failure_preserves_completed_turn_evidence(self):
        m = module(self, 'harbor')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root); backend = m.HarborBackend()
            row = {'turn': 1, 'turn_id': 't1', 'status': 'completed', 'artifacts': [], 'usage': {}}
            def fail(prepared, emit):
                prepared.state['result'] = {'trial_id': spec['trial_id'], 'status': 'completed', 'turns': [row], 'failure_reason': None}
                raise RuntimeError('native job interrupted after first turn')
            with mock.patch.object(m, 'runtime_check', return_value={}), mock.patch.object(m, 'integrations'), mock.patch.object(backend, 'execute', side_effect=fail):
                result = backend.execute_trial(spec, root / 'output', lambda event: None)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['turns'], [row])
            self.assertIn('native job interrupted', result['failure_reason'])

    def test_native_lifecycle_failure_cannot_be_masked_by_completed_local_turns(self):
        m = module(self, 'harbor')
        self.assertTrue(hasattr(m, 'validate_native_result'))
        step = types.SimpleNamespace(step_name='t1', exception_info=None)
        trial = types.SimpleNamespace(exception_info=None, step_results=[step])
        native = types.SimpleNamespace(trial_results=[trial])
        m.validate_native_result(native, ['t1'])
        trial.exception_info = {'exception_type': 'LifecycleFailure'}
        with self.assertRaisesRegex(ValueError, 'lifecycle'):
            m.validate_native_result(native, ['t1'])
        trial.exception_info = None; step.exception_info = {'exception_type': 'StepFailure'}
        with self.assertRaisesRegex(ValueError, 'step'):
            m.validate_native_result(native, ['t1'])

    def test_harbor_fingerprint_changes_with_actual_dependency_versions(self):
        m = module(self, 'harbor')
        first = mock.Mock(version='1.0', metadata={'Name': 'actual_dependency'})
        second = mock.Mock(version='1.1', metadata={'Name': 'actual_dependency'})
        with mock.patch.object(m.importlib.metadata, 'distributions', return_value=[first]):
            before = m.HarborBackend().fingerprint()
        with mock.patch.object(m.importlib.metadata, 'distributions', return_value=[second]):
            after = m.HarborBackend().fingerprint()
        self.assertNotEqual(before, after)

    def test_optional_native_log_mapping_never_uploads_other_host_directories(self):
        m = module(self, 'harbor')
        try:
            m.runtime_check({}); m.integrations()
        except (ValueError, ImportError) as error:
            self.skipTest('Optional exact-source Harbor runtime unavailable: ' + str(error))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); logs = root / 'agent'; logs.mkdir(); (logs / 'proof.json').write_text('{}')
            environment = m.HarborCodexEnvironment.__new__(m.HarborCodexEnvironment)
            environment.trial_paths = types.SimpleNamespace(agent_dir=logs, verifier_dir=root / 'verifier', artifacts_dir=root / 'artifacts', trial_dir=root)
            try:
                asyncio.run(environment.upload_dir(logs, '/logs/agent'))
            except ValueError as error:
                self.fail('Exact private log mapping rejected: ' + str(error))
            unrelated = root / 'host-credentials'; unrelated.mkdir(); (unrelated / 'auth.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'unsupported'):
                asyncio.run(environment.upload_dir(unrelated, '/logs/agent'))
    def test_optional_native_harbor_job_uses_real_steps_with_offline_client(self):
        h = module(self, 'harbor'); m = module(self)
        try:
            h.runtime_check({}); h.integrations()
        except (ValueError, ImportError) as error:
            self.skipTest('Optional exact-source Harbor runtime unavailable: ' + str(error))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); spec = fixture(root); commands = []; events = []
            identifier = '12345678-1234-1234-1234-123456789abc'
            class Process:
                returncode = 0
                def __init__(self, args, **kwargs):
                    commands.append(args); n = len(commands)
                    kwargs['stdout'].write(json.dumps({'type': 'thread.started', 'thread_id': identifier}) + '\n')
                    kwargs['stdout'].write(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': n * 100, 'cached_input_tokens': n * 70, 'output_tokens': n * 10}}) + '\n')
                def communicate(self, prompt, timeout):
                    (root / 'workspace/notes.md').write_text('Author-controlled offline handoff; no model called.')
            # Replace this module's client launcher only. Harbor lifecycle exec
            # keeps the real subprocess module and the official OS sandbox.
            launcher = types.SimpleNamespace(Popen=Process, PIPE=m.subprocess.PIPE, TimeoutExpired=m.subprocess.TimeoutExpired)
            evidence = {'rollout_found': True, 'reference_input_image_items': 1, 'image_items': 0}
            with mock.patch.object(m.LocalCodexBackend, 'doctor', return_value={'passed': True, 'model_called': False}), mock.patch.object(m.legacy().core, 'host_skill_paths', return_value=[]), mock.patch.object(m.legacy(), 'rollout_evidence', return_value=evidence), mock.patch.object(m, 'subprocess', launcher):
                result = h.HarborBackend().execute_trial(spec, root / 'output', events.append)
            self.assertEqual(result['status'], 'completed', result['failure_reason'])
            self.assertEqual([r['turn'] for r in result['turns']], [1, 2])
            self.assertEqual([e['turn'] for e in events if e['type'] == 'call_reserved'], [1, 2])
            self.assertEqual(commands[1][-3:], ['--', identifier, '-'])
            native = root / 'output/harbor-jobs/native'
            trials = [path for path in native.glob('*/result.json') if path.parent.name != 'native']
            self.assertEqual(len(trials), 1)
            actual = json.loads(trials[0].read_text())
            self.assertEqual([step['step_name'] for step in actual['step_results']], ['t1', 't2'])
            self.assertFalse(any(step.get('exception_info') for step in actual['step_results']))
            if destination := os.environ.get('SKILL_BENCH_NATIVE_EVIDENCE'):
                retained = Path(destination)
                shutil.copytree(root / 'output', retained)
                proof = {'model_calls': 0, 'offline_client_launches': len(commands), 'native_job': True,
                         'steps': [step['step_name'] for step in actual['step_results']],
                         'client_stdout_usage_and_rollout': 'author_controlled_fixture',
                         'source_provenance': h.runtime_check({}), 'backend': result['backend']}
                (retained / 'structural-proof.json').write_text(json.dumps(proof, indent=2) + '\n')

    def test_source_installer_rejects_a_dirty_or_wrong_repository(self):
        path = SRC.parent / 'scripts/install_harbor.py'
        self.assertTrue(path.is_file(), 'The explicit private-venv source installer is missing.')
        loader = importlib.util.spec_from_file_location('test_harbor_installer', path)
        installer = importlib.util.module_from_spec(loader); loader.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def output(args, **kwargs):
                if 'get-url' in args:
                    return 'https://github.com/harbor-framework/harbor.git\n'
                if 'rev-parse' in args:
                    return installer.SOURCE_SHA + '\n'
                return ' M pyproject.toml\n'
            with mock.patch.object(installer.subprocess, 'check_output', side_effect=output):
                with self.assertRaisesRegex(ValueError, 'modified'):
                    installer.validate_source(root)
            with mock.patch.object(installer.subprocess, 'check_output', return_value='https://untrusted.invalid/harbor\n'):
                with self.assertRaisesRegex(ValueError, 'official'):
                    installer.validate_source(root)


if __name__ == '__main__':
    unittest.main()
