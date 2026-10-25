"""The orchestrator reserves invocations and derives completion from evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_contracts import case
from skill_bench.contracts import content_hash
from skill_bench.experiment import load_experiment, prepare_experiment
from skill_bench.runner import independently_grade, run_experiment
from skill_bench.store import read_events


class FakeBackend:
    id = 'local_codex'
    capabilities = {'svg': True}
    calls = 0
    def fingerprint(self):
        return 'a' * 64
    def doctor(self, config):
        return {'passed': True, 'model_called': False}
    def execute_trial(self, spec, output, emit):
        Path(output).mkdir(parents=True, exist_ok=True)
        turns = []
        for number, turn in enumerate(spec['case']['turns'], 1):
            emit({'type': 'call_reserved', 'trial_id': spec['trial_id'], 'turn': number})
            self.calls += 1
            # Deliberately invalid image: execution success must not imply delivery.
            dest = Path(output) / f'turn-{number}/artifacts/a.png'
            dest.parent.mkdir(parents=True)
            dest.write_bytes(b'not an image')
            turns.append({'turn': number, 'status': 'completed', 'artifacts': [
                {'path': 'a.png', 'snapshot': dest.relative_to(output).as_posix(),
                 'sha256': content_hash(dest.read_bytes()), 'size': dest.stat().st_size}],
                'delivery': {'delivery_pass': True}, 'usage': {}})
        return {'trial_id': spec['trial_id'], 'status': 'completed', 'turns': turns,
                'backend': {'id': self.id, 'fingerprint': self.fingerprint()}, 'failure_reason': None}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        raw = (json.dumps(case()) + '\n').encode()
        (self.root / 'case.json').write_bytes(raw)
        suite = {'schema_version': 2, 'id': 'fixture', 'cases': [
            {'path': 'case.json', 'sha256': content_hash(raw)}]}
        (self.root / 'suite.json').write_text(json.dumps(suite))
        self.adapter = FakeBackend()
        with patch('skill_bench.experiment.backend', return_value=self.adapter):
            self.manifest = prepare_experiment(self.root / 'suite.json', self.root / 'run',
                arms={'none': None}, max_calls=2)

    def test_planning_does_not_invoke_models(self):
        result = run_experiment(self.root / 'run', adapter=self.adapter)
        self.assertEqual(result['state'], 'prepared')
        self.assertEqual(self.adapter.calls, 0)

    def test_invalid_image_not_promoted_to_delivery_success(self):
        result = run_experiment(self.root / 'run', execute=True, adapter=self.adapter)
        self.assertEqual(result['state'], 'completed_with_failures')
        recorded = json.loads((self.root / 'run/trials/example--r001--none/result.json').read_text())
        self.assertFalse(recorded['turns'][0]['delivery']['delivery_pass'])
        self.assertIsNone(recorded['turns'][0]['delivery']['quality_score'])
        calls = [e for e in read_events(self.root / 'run') if e['type'] == 'call_reserved']
        self.assertEqual(len(calls), 2)

    def test_existing_run_cannot_silently_retry(self):
        run_experiment(self.root / 'run', execute=True, adapter=self.adapter)
        with self.assertRaisesRegex(ValueError, 'retry|started'):
            run_experiment(self.root / 'run', execute=True, adapter=self.adapter)
        self.assertEqual(self.adapter.calls, 2)

    def test_manifest_change_is_rejected_before_execution(self):
        path = self.root / 'run/manifest.json'
        modified = json.loads(path.read_text())
        modified['limits']['max_calls'] = 54
        path.write_text(json.dumps(modified))
        with self.assertRaisesRegex(ValueError, 'manifest|seal'):
            load_experiment(self.root / 'run')

    def test_frozen_framework_mutation_is_rejected(self):
        path = self.root / 'run/framework/store.py'
        path.write_bytes(path.read_bytes() + b'\n# altered snapshot\n')
        with self.assertRaisesRegex(ValueError, 'framework'):
            load_experiment(self.root / 'run')

    def test_unlisted_framework_file_is_rejected(self):
        path = self.root / 'run/framework/unrecorded.py'
        path.write_text('print("unexpected")\n')
        with self.assertRaisesRegex(ValueError, 'framework'):
            load_experiment(self.root / 'run')

    def test_previous_arm_without_skill_is_rejected(self):
        with patch('skill_bench.experiment.backend', return_value=self.adapter):
            with self.assertRaisesRegex(ValueError, 'skill'):
                prepare_experiment(self.root / 'suite.json', self.root / 'bad',
                    arms={'previous': None}, max_calls=2)

    def test_duplicate_real_turn_is_rejected(self):
        result = {'status': 'completed', 'turns': [
            {'turn': 1, 'status': 'completed', 'artifacts': []},
            {'turn': 1, 'status': 'completed', 'artifacts': []}]}
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            independently_grade(self.root, case(), result)
