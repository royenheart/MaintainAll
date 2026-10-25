"""Verifier revisions cannot alter generation or omit their runtime identity."""
import copy
import unittest

import test_runner
from skill_bench.contracts import json_hash
from skill_bench.runner import load_regrade, regrade, run_experiment
from skill_bench.store import append_event, write_immutable


class RegradeTests(unittest.TestCase):
    def setUp(self):
        fixture = test_runner.RunnerTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root / 'run'
        run_experiment(self.root, execute=True, adapter=fixture.adapter)
        self.record = regrade(self.root, reopen_sources=True)

    def publish_fixture_revision(self, changes):
        record = copy.deepcopy(self.record)
        record.update(changes)
        record['id'] = json_hash({k: v for k, v in record.items() if k != 'id'})
        path = self.root / 'regrades' / (record['id'] + '.json')
        sha = write_immutable(path, record)
        append_event(self.root, {'type': 'regrade_frozen', 'id': record['id'], 'record_sha256': sha})
        return path

    def test_real_verifier_record_can_be_loaded(self):
        path = self.root / 'regrades' / (self.record['id'] + '.json')
        self.assertEqual(load_regrade(self.root, path), self.record)

    def test_reopened_record_requires_both_source_identities(self):
        for key in ('source_runtime_fingerprint', 'source_verifier_sha256'):
            with self.subTest(key=key):
                path = self.publish_fixture_revision({key: None})
                with self.assertRaisesRegex(ValueError, 'source.*identity'):
                    load_regrade(self.root, path)

    def test_mechanical_record_cannot_claim_a_generation_call(self):
        path = self.publish_fixture_revision({'generation_calls': 1})
        with self.assertRaisesRegex(ValueError, 'zero generation'):
            load_regrade(self.root, path)

    def test_no_reopen_record_cannot_keep_a_source_runtime(self):
        path = self.publish_fixture_revision({'reopen_sources': False})
        with self.assertRaisesRegex(ValueError, 'source.*identity'):
            load_regrade(self.root, path)
