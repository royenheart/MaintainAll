"""Evidence may fail or remain unknown; it cannot be overwritten or retried silently."""

import tempfile
import unittest
from pathlib import Path

from skill_bench.store import append_event, load_results, read_events, write_immutable


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_locked_record_cannot_be_replaced(self):
        path = self.root / "rating.json"
        write_immutable(path, {"score": 1})
        with self.assertRaisesRegex(ValueError, "immutable"):
            write_immutable(path, {"score": 2})

    def test_reserved_call_cannot_be_reserved_again(self):
        value = {"type": "call_reserved", "trial_id": "a", "turn": 1}
        append_event(self.root, value, max_calls=2)
        with self.assertRaisesRegex(ValueError, "reserved"):
            append_event(self.root, value, max_calls=2)

    def test_hard_budget_prevents_next_call(self):
        append_event(self.root, {"type": "call_reserved", "trial_id": "a", "turn": 1}, max_calls=1)
        with self.assertRaisesRegex(ValueError, "budget"):
            append_event(self.root, {"type": "call_reserved", "trial_id": "b", "turn": 1}, max_calls=1)

    def test_truncated_event_is_not_silently_ignored(self):
        (self.root / "events.jsonl").write_text('{"type":"call_reserved"')
        with self.assertRaisesRegex(ValueError, "event"):
            read_events(self.root)

    def test_event_tamper_is_detected(self):
        append_event(self.root, {"type": "trial_started", "trial_id": "a"})
        path = self.root / "events.jsonl"
        path.write_text(path.read_text().replace("trial_started", "trial_completed"))
        with self.assertRaisesRegex(ValueError, "hash"):
            read_events(self.root)

    def test_result_seal_and_directory_identity_are_required(self):
        path = self.root / 'trials/a/result.json'
        sha = write_immutable(path, {'trial_id': 'b', 'status': 'completed'})
        with self.assertRaisesRegex(ValueError, 'seal'):
            load_results(self.root)
        write_immutable(path.with_name('result-seal.json'), {'sha256': sha})
        with self.assertRaisesRegex(ValueError, 'identity'):
            load_results(self.root)
