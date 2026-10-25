import json
import struct
import tempfile
import unittest
from pathlib import Path

from skill_bench.grading import calibrate, grade_delivery, measure_relation


class DeliveryTests(unittest.TestCase):
    def test_valid_container_is_not_quality_or_editability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scene.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"><rect width="20" height="10"/></svg>')
            (root / 'notes.md').write_text('Self-assessed quality: 2/2.')
            case = {'turns': [{'artifacts': [{'path': 'scene.svg', 'format': 'svg', 'kind': 'editable'}, {'path': 'notes.md', 'format': 'md', 'kind': 'notes'}]}], 'limits': {'max_file_bytes': 8192, 'max_workspace_bytes': 16384}}
            result = grade_delivery(root, case, 1)
            self.assertTrue(result['delivery_pass'])
            self.assertEqual(result['quality_status'], 'unassessed')
            self.assertIsNone(result['quality_score'])
            self.assertFalse(result['source_editability_verified'])

    def test_missing_oversize_wrong_size_and_escape_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scene.svg').write_text('<svg width="20" height="10"/>')
            case = {'turns': [{'artifacts': [{'path': 'missing.png', 'format': 'png', 'kind': 'preview'}, {'path': 'scene.svg', 'format': 'svg', 'kind': 'preview', 'width': 30, 'height': 10}, {'path': '../escape.md', 'format': 'md', 'kind': 'notes'}]}], 'limits': {'max_file_bytes': 20, 'max_workspace_bytes': 1000}}
            result = grade_delivery(root, case, 1)
            self.assertFalse(result['delivery_pass'])
            self.assertEqual(len(result['artifacts']), 3)
            self.assertTrue(all(not row['pass'] for row in result['artifacts']))

    def test_relation_measurement_is_not_visual_quality(self):
        good = measure_relation({'kind': 'shared_baseline', 'a': [18, 143], 'b': [258, 143], 'tolerance': 2})
        bad = measure_relation({'kind': 'shared_baseline', 'a': [18, 143], 'b': [258, 66], 'tolerance': 2})
        self.assertTrue(good['relation_pass'])
        self.assertFalse(bad['relation_pass'])
        self.assertEqual(good['quality_status'], 'unassessed')
        self.assertEqual(measure_relation({'kind': 'unknown'})['status'], 'unverifiable')

    def test_calibration_positive_negative_and_invariance(self):
        suite = Path(__file__).resolve().parents[2] / 'art_creation'
        result = calibrate(suite)
        self.assertTrue(result['pass'])
        self.assertEqual(len(result['pairs']), 2)
        self.assertTrue(all(p['positive_pass'] and not p['negative_pass'] and p['invariance_pass'] for p in result['pairs']))

class EvidenceBoundaryTests(unittest.TestCase):
    def test_png_header_without_pixels_does_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'view.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'not actual pixels')
            case = {'turns': [{'artifacts': [{'path': 'view.png', 'format': 'png', 'kind': 'preview'}]}]}
            self.assertFalse(grade_delivery(root, case, 1)['delivery_pass'])

    def test_solver_assertions_and_symlink_never_establish_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'self.json').write_text('{"quality":2,"source_editability_verified":true}')
            (root / 'alias.json').symlink_to(root / 'self.json')
            case = {'turns': [{'artifacts': [{'path': 'self.json', 'format': 'json', 'kind': 'evidence'}]}]}
            result = grade_delivery(root, case, 1)
            self.assertTrue(result['delivery_pass'])
            self.assertEqual(result['quality_status'], 'unassessed')
            self.assertFalse(result['source_editability_verified'])
            case['turns'][0]['artifacts'][0]['path'] = 'alias.json'
            self.assertFalse(grade_delivery(root, case, 1)['delivery_pass'])

class SvgEncodingBoundaryTests(unittest.TestCase):
    def test_utf16_entity_source_is_rejected_before_xml_expansion(self):
        from skill_bench.grading import _svg
        xml = '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE svg [<!ENTITY x "expanded">]><svg width="32" height="24"><text>&x;</text></svg>'
        with self.assertRaises(ValueError):
            _svg(xml.encode('utf-16'))

    def test_utf8_dtd_and_entity_declarations_are_rejected(self):
        from skill_bench.grading import _svg
        for declaration in ('<!DOCTYPE svg [<!ENTITY x "expanded">]>', '<!ENTITY x "expanded">'):
            with self.subTest(declaration=declaration), self.assertRaisesRegex(ValueError, 'entities'):
                _svg((declaration + '<svg width="32" height="24"/>').encode('utf-8'))

    def test_valid_utf8_svg_with_bom_remains_supported(self):
        from skill_bench.grading import _svg
        _, dimensions = _svg(b'\xef\xbb\xbf<svg width="32" height="24"/>')
        self.assertEqual(dimensions, (32, 24))
