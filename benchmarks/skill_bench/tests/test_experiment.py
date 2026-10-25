"""The unit of comparison is a paired task episode with a frozen order."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_bench.experiment import load_experiment, prepare_experiment, trial_schedule
from skill_bench.store import append_event, state, write_immutable


class ExperimentTests(unittest.TestCase):
    def test_commit_identity_is_sealed_and_unsafe_metadata_is_rejected(self):
        from test_runner import RunnerTests
        fixture = RunnerTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        provenance = {'candidate_sha': 'a' * 40, 'previous_sha': 'b' * 40,
            'trusted_sha': 'c' * 40, 'source_run_id': 123, 'source_run_attempt': 1,
            'protocol_id': 'main-first-parent-paired-v1', 'tracking_key': 'd' * 64}
        with patch('skill_bench.experiment.backend', return_value=fixture.adapter):
            prepare_experiment(fixture.root / 'suite.json', fixture.root / 'tracked',
                arms={'none': None}, max_calls=2, commit_provenance=provenance)
            for index, invalid in enumerate((dict(provenance, candidate_sha='main'),
                    dict(provenance, source_run_id=True), dict(provenance, command='unsafe'))):
                with self.assertRaises(ValueError):
                    prepare_experiment(fixture.root / 'suite.json', fixture.root / f'invalid-{index}',
                        arms={'none': None}, max_calls=2, commit_provenance=invalid)
        self.assertEqual(load_experiment(fixture.root / 'tracked')['commit_provenance'], provenance)
        manifest = fixture.root / 'tracked/manifest.json'
        data = json.loads(manifest.read_text())
        data['commit_provenance']['candidate_sha'] = 'e' * 40
        manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'seal'):
            load_experiment(fixture.root / 'tracked')

    def test_each_arm_occupies_each_position_in_three_repeat_blocks(self):
        rows = trial_schedule(["costume"], ["none", "previous", "candidate"], 3, 13)
        self.assertEqual(len(rows), 9)
        for index in range(3):
            self.assertEqual({rows[offset + index]["arm"] for offset in (0, 3, 6)},
                             {"none", "previous", "candidate"})

    def test_order_is_reproducible_and_trials_unique(self):
        rows = trial_schedule(["costume", "poster"], ["none", "previous", "candidate"], 3, 17)
        self.assertEqual(rows, trial_schedule(["costume", "poster"], ["none", "previous", "candidate"], 3, 17))
        self.assertEqual(len(rows), len({r["trial_id"] for r in rows}))

    def test_result_rows_determine_completion_not_manifest_label(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {"state": "running", "schedule": [{"trial_id": "a"}]}
            sha = write_immutable(root / "trials/a/result.json", {"trial_id": "a", "status": "completed"})
            write_immutable(root / "trials/a/result-seal.json", {"sha256": sha})
            self.assertEqual(state(root, manifest)["state"], "completed")

    def test_unfinished_reserved_call_cannot_be_reported_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = {"schedule": [{"trial_id": "a"}]}
            append_event(root, {"type": "run_started"})
            append_event(root, {"type": "call_reserved", "trial_id": "a", "turn": 1}, 1)
            append_event(root, {"type": "run_finished", "reason": "interrupted"})
            self.assertEqual(state(root, manifest)["state"], "interrupted")
