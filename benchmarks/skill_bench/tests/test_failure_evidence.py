"""Failed-turn evidence is bounded and never promotes stale files into output."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


class FailureEvidenceTests(unittest.TestCase):
    def stream(self, root, events):
        path = root / 'events.jsonl'
        path.write_text(''.join(json.dumps(event) + '\n' for event in events))
        return path

    def test_valid_transport_failure_has_no_model_output_and_no_raw_text(self):
        from skill_bench.failure_evidence import classify_cli_stream
        with tempfile.TemporaryDirectory() as directory:
            path = self.stream(Path(directory), [
                {'type': 'thread.started', 'thread_id': 'private-thread-identifier'},
                {'type': 'turn.started'},
                {'type': 'error', 'message': 'Discovery request failed; reconnecting. secret-user@example.test'},
                {'type': 'turn.failed', 'error': {'message': 'Discovery connection failed at /home/private/auth.json'}},
            ])
            value = classify_cli_stream(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(value['model_output'], 'absent')
            self.assertEqual(value['stream_integrity'], 'valid')
            self.assertEqual(value['failure_codes'], ['connection', 'route-discovery'])
            self.assertNotIn('private', json.dumps(value))
            self.assertNotIn('secret-user', json.dumps(value))

    def test_model_message_or_tool_action_marks_failed_stream_as_partial(self):
        from skill_bench.failure_evidence import classify_cli_stream, turn_evidence_scope
        with tempfile.TemporaryDirectory() as directory:
            path = self.stream(Path(directory), [
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Adjusting the shoulder relation.'}},
                {'type': 'item.started', 'item': {'type': 'command_execution', 'command': 'draw-preview'}},
                {'type': 'turn.failed', 'error': {'message': 'Connection failed'}},
            ])
            value = classify_cli_stream(path)
            self.assertEqual(value['model_output'], 'observed')
            self.assertEqual(turn_evidence_scope('failed', value)['evidence_status'], 'partial-model-output')
            self.assertFalse(turn_evidence_scope('failed', value)['withhold_turn_artifacts'])

    def test_missing_malformed_mismatched_and_unknown_events_never_claim_absence(self):
        from skill_bench.failure_evidence import classify_cli_stream, turn_evidence_scope
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [root / 'missing.jsonl']
            bad = root / 'malformed.jsonl'
            bad.write_text('{"type":"turn.started"}\n{partial\n')
            cases.append(bad)
            unknown = self.stream(root, [{'type': 'future.model.event'}])
            cases.append(unknown)
            for path in cases:
                value = classify_cli_stream(path)
                self.assertEqual(value['model_output'], 'unknown')
                self.assertFalse(turn_evidence_scope('failed', value)['withhold_turn_artifacts'])
            self.assertEqual(classify_cli_stream(unknown, expected_sha256='0' * 64)['stream_integrity'], 'hash-mismatch')

    def test_byte_and_link_bounds_never_yield_verified_absence(self):
        from skill_bench.failure_evidence import classify_cli_stream
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.stream(root, [{'type': 'turn.failed', 'error': {'message': 'Discovery failed'}}])
            self.assertEqual(classify_cli_stream(path, max_bytes=1)['model_output'], 'unknown')
            link = root / 'linked.jsonl'
            link.symlink_to(path)
            self.assertEqual(classify_cli_stream(link)['model_output'], 'unknown')

    def test_cli_scope_is_explicit_and_defaults_remain_legacy(self):
        from skill_bench.cli import parser
        for command in ('review', 'local-report'):
            base = [command, '--run', '/tmp/run', '--output', '/tmp/new-packet']
            self.assertEqual(parser().parse_args(base).evidence_scope, 'legacy')
            self.assertEqual(parser().parse_args(base + ['--evidence-scope', 'failed-turn-v1']).evidence_scope, 'failed-turn-v1')

    def test_unfamiliar_known_item_payload_cannot_prove_absent_model_output(self):
        from skill_bench.failure_evidence import classify_cli_stream, turn_evidence_scope
        items = [{'type': 'agent_message', 'text': {'future': 'payload'}}, {'type': 'reasoning', 'text': []}, {'type': 'command_execution', 'command': {'shell': 'future'}}, {'type': 'mcp_tool_call', 'tool': []}, {'type': 'file_change', 'changes': ['future-shape']}, {'type': 'todo_list', 'items': 'future-shape'}, {'type': 'web_search', 'query': {'future': 'shape'}}]
        for item in items:
            with self.subTest(item=item['type']), tempfile.TemporaryDirectory() as directory:
                path = self.stream(Path(directory), [{'type': 'item.completed', 'item': item}, {'type': 'turn.failed'}])
                value = classify_cli_stream(path)
                self.assertEqual(value['model_output'], 'unknown')
                self.assertFalse(turn_evidence_scope('failed', value)['withhold_turn_artifacts'])

    def test_observed_supported_output_survives_an_unfamiliar_payload(self):
        from skill_bench.failure_evidence import classify_cli_stream
        with tempfile.TemporaryDirectory() as directory:
            path = self.stream(Path(directory), [{'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'Actual output'}}, {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': {'future': 'shape'}}}])
            self.assertEqual(classify_cli_stream(path)['model_output'], 'observed')


if __name__ == '__main__':
    unittest.main()
