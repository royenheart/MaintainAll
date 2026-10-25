"""Independent original captures must not mix verifier modifications into scoring."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skill_bench.review import export_review, canonical_hash, validate_packet_mapping
from skill_bench.report import build_report
from skill_bench.store import load_results
from test_review import fixture, pixel_png


class VisualReviewTests(unittest.TestCase):
    def test_review_cannot_be_reattributed_to_a_different_capture_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'run'
            root.mkdir()
            manifest = fixture(root)
            results = load_results(root)
            dest = Path(tmp) / 'packet'
            revision = {'id': 'f' * 64, 'results': results}
            with patch('skill_bench.experiment.load_experiment', return_value=manifest), patch('skill_bench.runner.load_regrade', return_value=revision):
                packet = export_review(root, dest, seed=3, regrade_path=root / 'regrades/example.json')
            mapping = json.loads(next((root / 'reviews').glob('*.arm-map.json')).read_text())
            self.assertEqual(packet['source_revision'], revision['id'])
            self.assertEqual(mapping['source_revision'], revision['id'])
            document = json.loads((dest / 'ratings-template.json').read_text())
            document['reviewer'].update(id='independent-reviewer', **{'class': 'agent'})
            for rating in document['ratings']:
                artifact = next(e for e in packet['entries'] if e['id'] == rating['entry'])['turns'][0]['artifacts'][0]
                rating.update(evidence=[{'path': artifact['path'], 'sha256': artifact['sha256']}], reason='Protocol regression fixture, no quality conclusion.')
            for rating in document['pairs']:
                artifact = packet['entries'][0]['turns'][0]['artifacts'][0]
                rating.update(evidence=[{'path': artifact['path'], 'sha256': artifact['sha256']}], reason='Protocol regression fixture, no preference.')
            bundle = {'packet': packet, 'document': document, 'arm_map': mapping}
            for selected in (None, 'a' * 64):
                manifest['mechanical_verifier'] = {'regrade_id': selected}
                with self.assertRaisesRegex(ValueError, 'source revision'):
                    build_report(manifest, results, [bundle])
            manifest['mechanical_verifier'] = {'regrade_id': revision['id']}
            report = build_report(manifest, results, [bundle])
            self.assertTrue(all(r['source_revision'] == revision['id'] for r in report['ratings'] + report['pairs']))
            self.assertTrue(all(r['judge']['evidence_scope'] == 'independent-source-captures' for r in report['ratings']))
            # Run-specific capture IDs bind the records without fragmenting
            # histories that have the same actual verifier and judge conditions.
            other = json.loads(json.dumps(bundle))
            other['packet']['source_revision'] = other['arm_map']['source_revision'] = 'a' * 64
            other['arm_map']['packet_sha256'] = canonical_hash(other['packet'])
            manifest['mechanical_verifier']['regrade_id'] = 'a' * 64
            next_report = build_report(manifest, results, [other])
            self.assertEqual([r['cohort_id'] for r in report['ratings']], [r['cohort_id'] for r in next_report['ratings']])
            changed = dict(mapping, source_revision='a' * 64)
            with self.assertRaisesRegex(ValueError, 'source revision'):
                validate_packet_mapping(packet, changed)

    def test_modified_scene_and_svg_pixels_stay_out_of_the_quality_gallery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'run'
            root.mkdir()
            manifest = fixture(root)
            results = load_results(root)
            images = {}
            for index, label in enumerate(('front', 'side', 'camera', 'edited-front', 'source', 'edited')):
                raw = pixel_png(100 + index)
                path = root / (label + '.png')
                path.write_bytes(raw)
                images[label] = {'path': path.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
            for result in results:
                result['turns'][0]['source_verification'] = [{
                    'format': 'blend', 'source_reopen_verified': True, 'source_editability_verified': True,
                    'scope': 'One verifier-created location.x edit; exclude modified pixels from design judgments.',
                    'rendered': images}]
            revision = {'id': 'f' * 64, 'results': results}
            with patch('skill_bench.experiment.load_experiment', return_value=manifest), patch('skill_bench.runner.load_regrade', return_value=revision):
                packet = export_review(root, Path(tmp) / 'packet', seed=1, regrade_path=root / 'regrades/example.json')
            for entry in packet['entries']:
                captures = [item for item in entry['turns'][0]['artifacts'] if item.get('kind') == 'independent-source-capture']
                self.assertEqual({item['name'] for item in captures}, {'Independent capture / front', 'Independent capture / side', 'Independent capture / camera'})
                hashes = {item['sha256'] for item in captures}
                self.assertNotIn(images['edited']['sha256'], hashes)
                self.assertNotIn(images['edited-front']['sha256'], hashes)
                self.assertNotIn('trial-candidate', json.dumps(packet))

    def test_native_revision_images_still_require_inventory_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'run'
            root.mkdir()
            manifest = fixture(root)
            results = load_results(root)
            path = root / 'capture.png'
            path.write_bytes(pixel_png(10))
            for result in results:
                result['turns'][0]['source_verification'] = [{'format': 'html', 'rendered': {'frame-1': {
                    'path': path.name, 'sha256': '0' * 64, 'size': path.stat().st_size}}}]
            with patch('skill_bench.experiment.load_experiment', return_value=manifest), patch('skill_bench.runner.load_regrade', return_value={'id': 'f' * 64, 'results': results}):
                with self.assertRaisesRegex(ValueError, 'hash'):
                    export_review(root, Path(tmp) / 'packet', seed=2, regrade_path=root / 'regrades/example.json')
