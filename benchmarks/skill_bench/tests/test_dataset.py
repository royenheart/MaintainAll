import base64
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from skill_bench.trajectory import extract_users


class TrajectoryTests(unittest.TestCase):
    def test_only_user_messages_and_private_attachments(self):
        image = b'fake image fixture'
        rows = [
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'Keep the chosen border; change only the glow.'}, {'type': 'input_image', 'image_url': 'data:image/png;base64,' + base64.b64encode(image).decode()}]}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'I choose red.'}]}},
            {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'Duplicate wrapper'}},
            {'type': 'response_item', 'payload': {'type': 'function_call', 'arguments': 'Do not treat as user'}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'log.jsonl'
            log.write_text('\n'.join(json.dumps(r) for r in rows))
            result = extract_users([log], root / 'private')
            self.assertEqual(result['intent_messages'], 1)
            self.assertEqual(result['attachments_available'], 1)
            messages = [json.loads(x) for x in (root / 'private' / 'users.jsonl').read_text().splitlines()]
            self.assertEqual(messages[0]['line'], 1)
            self.assertEqual(messages[0]['attachments'][0]['sha256'], hashlib.sha256(image).hexdigest())
            self.assertNotIn('token', result)

    def test_missing_path_is_unavailable_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'log.jsonl'
            content = '<image path="/definitely/missing/reference.png"></image>'
            row = {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': content}]}}
            log.write_text(json.dumps(row))
            result = extract_users([log], root / 'private')
            message = json.loads((root / 'private' / 'users.jsonl').read_text())
            self.assertEqual(result['attachments_unavailable'], 1)
            self.assertEqual(message['attachments'][0]['status'], 'asset_unavailable')
            self.assertFalse((root / 'private' / 'assets').exists())

    def test_context_is_not_a_preference_and_malformed_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / 'log.jsonl'
            row = {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': '# AGENTS.md instructions'}]}}
            log.write_text(json.dumps(row) + '\ninvalid')
            result = extract_users([log], root / 'private')
            self.assertEqual(result['intent_messages'], 0)
            self.assertEqual(result['context_messages'], 1)
            self.assertEqual(result['malformed_lines'], 1)


class SuiteTests(unittest.TestCase):
    def test_eight_frozen_cases_and_requirement_alignment(self):
        root = Path(__file__).resolve().parents[2] / 'art_creation'
        suite = json.loads((root / 'suite.json').read_text())
        self.assertEqual(len(suite['cases']), 8)
        splits = {'development': 0, 'holdout': 0}
        for ref in suite['cases']:
            raw = (root / ref['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), ref['sha256'])
            case = json.loads(raw)
            splits[case['split']] += 1
            requirements = {r['id']: r for r in case['requirements']}
            for requirement in requirements.values():
                self.assertIn(requirement['quote'], case['turns'][requirement['turn'] - 1]['prompt'])
            for atom in case['atoms']:
                self.assertTrue(atom['requirement_ids'])
                self.assertTrue(all(x in requirements for x in atom['requirement_ids']))
                self.assertTrue(atom['active_turns'])
                self.assertTrue(all(requirements[r]['turn'] <= t for r in atom['requirement_ids'] for t in atom['active_turns']))
            for asset in case['assets']:
                path = (root / ref['path']).parent / asset['path']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), asset['sha256'])
        self.assertEqual(splits, {'development': 6, 'holdout': 2})

    def test_editorial_hierarchy_is_not_scored_before_user_requires_it(self):
        root = Path(__file__).resolve().parents[2] / 'art_creation'
        case = json.loads((root / 'cases/editorial-transfer/case.json').read_text())
        atom = next(x for x in case['atoms'] if x['id'] == 'reading-hierarchy')
        self.assertEqual(atom['active_turns'], [2, 3])

class PrivacyBoundaryTests(unittest.TestCase):
    def test_public_trajectory_uses_hashes_instead_of_private_session_ids(self):
        root = Path(__file__).resolve().parents[2] / 'art_creation/trajectory'
        suite = json.loads((root / 'suite.json').read_text())
        for ref in suite['cases']:
            raw = (root / ref['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), ref['sha256'])
            self.assertIsNone(re.search(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', raw.decode()))
            provenance = json.loads(raw)['provenance']
            for key in ('source_session_sha256', 'source_thread_sha256'):
                self.assertRegex(provenance[key], r'^[0-9a-f]{64}$')
            self.assertTrue(provenance['reference_replacement'])

    def test_private_extraction_rejects_git_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.git').write_text('gitdir: /irrelevant/worktree')
            log = root / 'log.jsonl'
            log.write_text('')
            with self.assertRaisesRegex(ValueError, 'outside a Git'):
                extract_users([log], root / 'private')
            with tempfile.TemporaryDirectory() as second:
                alias = Path(second) / 'alias'
                alias.symlink_to(root, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, 'outside a Git'):
                    extract_users([log], alias / 'private')
