import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from skill_bench.legacy import import_legacy
from skill_bench.report import build_report
from skill_bench.store import load_results


def fixture(root):
    image = Path(__file__).resolve().parents[2] / 'art_creation/calibration/attached-feature.png'
    raw = image.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    card = {'schema_version': 1, 'id': 'study', 'attachments': [{'id': 'ref', 'path': '../input.png', 'staged_path': 'inputs/ref.png', 'sha256': digest, 'license': 'CC0', 'source': 'fixture'}], 'rounds': [{'prompt': 'Show a supported feature.', 'attachments': ['ref'], 'required_artifacts': [{'path': 'view.png', 'format': 'png', 'kind': 'preview'}]}, {'prompt': 'Keep the feature; reduce its speed.', 'attachments': [], 'required_artifacts': [{'path': 'view.png', 'format': 'png', 'kind': 'preview'}]}], 'rubric': [{'id': 'supported', 'criterion': 'Feature is visibly supported.', 'anchors': {'0': 'Absent.', '1': 'Ambiguous.', '2': 'Supported.'}}]}
    manifest = {'schema_version': 1, 'state': 'running', 'model': 'fixture-model', 'effort': 'fixture', 'cards': [card], 'skills': {'old': {'sha256': 'a' * 64, 'files': {}}, 'new': {'sha256': 'b' * 64, 'files': {}}}, 'max_cli_calls': 4, 'seed': None, 'provider_snapshot': None}
    (root / 'manifest.json').write_text(json.dumps(manifest))
    for arm in ('old', 'new'):
        for turn in (1, 2):
            path = root / arm / 'study' / f'round{turn}'
            (path / 'artifacts/inputs').mkdir(parents=True)
            (path / 'artifacts/view.png').write_bytes(raw)
            (path / 'artifacts/inputs/ref.png').write_bytes(raw)
            usage = {'input_tokens': 10 if turn == 1 else 4, 'cached_input_tokens': 2, 'uncached_input_tokens': 8 if turn == 1 else 2, 'output_tokens': 3, 'usage_status': 'initial_thread_total' if turn == 1 else 'thread_total_delta'}
            result = {'arm': arm, 'task': 'study', 'turn': turn, 'status': 'completed', 'elapsed_seconds': 1.25, 'thread_id': 'private-thread', 'usage': usage, 'reported_cumulative_usage': {'input_tokens': 10 if turn == 1 else 14}, 'inputs_unchanged': True, 'outcome': {'delivery_pass': True, 'source_editability_verified': False, 'quality_scores': {'supported': 2}, 'artifacts': [{'path': 'view.png', 'kind': 'preview', 'sha256': digest, 'bytes': len(raw), 'passed': True}]}, 'capture': {'passed': True, 'artifacts': [{'path': 'view.png', 'sha256': digest, 'bytes': len(raw), 'capture_status': 'copied'}]}}
            (path / 'result.json').write_text(json.dumps(result))
    return manifest


class LegacyTests(unittest.TestCase):
    def test_historical_usage_and_quality_are_not_reinterpreted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            fixture(source)
            before = (source / 'manifest.json').read_bytes()
            manifest = import_legacy(source, root / 'imported')
            results = load_results(root / 'imported')
            self.assertEqual(len(results), 2)
            self.assertEqual({a['id'] for a in manifest['arms']}, {'previous', 'candidate'})
            self.assertEqual(manifest['import_mode'], 'historical_v1')
            self.assertTrue(manifest['legacy'])
            self.assertEqual(manifest['legacy_source_state'], 'running')
            self.assertEqual(sum(t['usage']['input_tokens'] for r in results for t in r['turns']), 28)
            self.assertTrue(all(r['quality_status'] == 'unassessed' for r in results))
            self.assertEqual((source / 'manifest.json').read_bytes(), before)
            report = build_report(manifest, results)
            self.assertEqual(report['sample_sizes']['turn_observations'], 4)
            self.assertEqual(len(report['ratings']), 0)
            self.assertTrue(all(t['quality_status'] == 'unassessed' for t in report['trials']))
            self.assertEqual(manifest['provider_sampling_seed'], None)
            self.assertEqual(manifest['backend_fingerprint'], 'unknown')

    def test_hash_mismatch_missing_snapshot_and_existing_output_fail(self):
        for failure in ('mismatch', 'missing', 'existing'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / 'source'
                source.mkdir()
                fixture(source)
                target = root / 'imported'
                if failure == 'mismatch':
                    (source / 'old/study/round1/artifacts/view.png').write_bytes(b'changed')
                elif failure == 'missing':
                    (source / 'old/study/round1/artifacts/view.png').unlink()
                else:
                    target.mkdir()
                with self.assertRaises(ValueError):
                    import_legacy(source, target)

    def test_unknown_usage_is_not_cumulative_sum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            fixture(source)
            p = source / 'old/study/round2/result.json'
            r = json.loads(p.read_text())
            r.pop('usage')
            p.write_text(json.dumps(r))
            import_legacy(source, root / 'imported')
            r = next(x for x in load_results(root / 'imported') if x['arm'] == 'previous')
            self.assertIsNone(r['turns'][1]['usage']['input_tokens'])
            self.assertEqual(r['turns'][1]['legacy_usage_status'], 'unknown')

    def test_new_anonymous_review_can_load_imported_snapshots(self):
        from skill_bench.review import export_review
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            fixture(source)
            import_legacy(source, root / 'imported')
            packet = export_review(root / 'imported', root / 'packet', seed=7)
            self.assertEqual(len(packet['entries']), 2)
            self.assertEqual(len(packet['references']), 1)
            self.assertEqual(sum(len(t['artifacts']) for e in packet['entries'] for t in e['turns']), 4)

class ImportIsolationTests(unittest.TestCase):
    def test_import_cannot_write_inside_original_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            source.mkdir()
            fixture(source)
            with self.assertRaisesRegex(ValueError, 'outside its source'):
                import_legacy(source, source / 'imported')
            self.assertFalse((source / 'imported').exists())

class ReadonlyMountTests(unittest.TestCase):
    def test_originally_excluded_readonly_input_is_hash_checked_from_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            fixture(source)
            path = source / 'old/study/round1/artifacts/inputs/ref.png'
            target = source / 'old/study/workspace/inputs/ref.png'
            target.parent.mkdir(parents=True)
            path.rename(target)
            manifest = import_legacy(source, root / 'imported')
            self.assertEqual(manifest['cases'][0]['assets'][0]['legacy_evidence_source'], 'old/study/workspace/inputs/ref.png')
            target.write_bytes(b'modified mounted input')
            with self.assertRaisesRegex(ValueError, 'hash'):
                import_legacy(source, root / 'second-import')
