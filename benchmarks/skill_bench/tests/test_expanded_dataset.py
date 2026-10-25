"""Frozen task coverage without reading legacy holdout prompts or invoking a model."""

import hashlib
import json
import struct
import unittest
from collections import Counter
from pathlib import Path

from skill_bench.contracts import load_suite
from skill_bench.backends.local_codex import LocalCodexBackend, limits


ROOT = Path(__file__).resolve().parents[2] / 'art_creation' / 'expanded'


def read_json(path):
    return json.loads(path.read_text())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExpandedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = load_suite(ROOT / 'suite.json')
        cls.cases = cls.suite['cases']
        cls.matrix = read_json(ROOT / 'matrix.json')
        cls.assets = read_json(ROOT / 'assets' / 'manifest.json')['assets']

    def test_frozen_release_counts_and_split(self):
        self.assertEqual(self.suite['id'], 'art-creation-expanded-v3')
        self.assertEqual(len(self.cases), 16)
        self.assertEqual(Counter(c['split'] for c in self.cases),
                         {'development': 12, 'holdout': 4})
        self.assertEqual(sum(len(c['turns']) for c in self.cases), 48)
        self.assertEqual(sum(len(c['atoms']) for c in self.cases), 141)
        self.assertEqual(sum(len(c['requirements']) for c in self.cases), 194)
        self.assertTrue(all(len(c['turns']) == 3 for c in self.cases))

    def test_manifest_tracks_exact_case_and_suite_bytes(self):
        self.assertEqual(self.matrix['suite_sha256'], sha256(ROOT / 'suite.json'))
        self.assertEqual(self.matrix['suite_id'], self.suite['id'])
        self.assertEqual(self.matrix['case_count'], 16)
        rows = {row['id']: row for row in self.matrix['cases']}
        self.assertEqual(set(rows), {case['id'] for case in self.cases})
        for case in self.cases:
            row = rows[case['id']]
            self.assertEqual(row['case_sha256'], case['_case_sha256'])
            self.assertEqual(row['atoms'], len(case['atoms']))
            self.assertEqual(row['split'], case['split'])
            self.assertEqual(row['capabilities'], case['capabilities'])
            self.assertEqual(row['rating_dimensions'],
                             sorted({atom['dimension'] for atom in case['atoms']}))

    def test_required_capability_groups_are_distinct(self):
        groups = Counter()
        for case in self.cases:
            capabilities = set(case['capabilities'])
            self.assertTrue({'real_images', 'exact_resume'} <= capabilities)
            self.assertTrue(all(LocalCodexBackend.capabilities.get(name)
                                for name in capabilities))
            if 'blender' in capabilities:
                self.assertIn('native_scene_reopen', capabilities)
                self.assertNotIn('svg', capabilities)
                groups['blender'] += 1
            elif 'browser_capture' in capabilities:
                self.assertIn('playable_motion', capabilities)
                self.assertNotIn('svg', capabilities)
                groups['browser'] += 1
            else:
                self.assertIn('svg', capabilities)
                groups['static'] += 1
        self.assertEqual(groups, {'static': 10, 'browser': 3, 'blender': 3})
        self.assertEqual(dict(groups), self.matrix['backend_groups'])

    def test_holdouts_span_reference_avatar_browser_and_native_domains(self):
        holdouts = [c for c in self.cases if c['split'] == 'holdout']
        self.assertEqual({c['provenance']['domain'] for c in holdouts},
                         {'reference_interpretation', 'costume_and_avatar',
                          'browser_interaction', 'native_3d'})
        self.assertTrue(all('evaluator-only' in c['provenance']['holdout_policy']
                            for c in holdouts))

    def test_requirements_quote_actual_prompts_and_never_activate_early(self):
        for case in self.cases:
            requirements = {r['id']: r for r in case['requirements']}
            for requirement in requirements.values():
                self.assertIn(requirement['quote'],
                              case['turns'][requirement['turn'] - 1]['prompt'])
            for atom in case['atoms']:
                first_known = max(requirements[r]['turn']
                                  for r in atom['requirement_ids'])
                self.assertGreaterEqual(min(atom['active_turns']), first_known)
                for turn_index in atom['active_turns']:
                    declared = {a['path'] for a in case['turns'][turn_index - 1]['artifacts']}
                    self.assertTrue(set(atom['evidence']['required_artifacts']) <= declared)
            self.assertTrue(any(min(a['active_turns']) == 2 for a in case['atoms']))
            self.assertTrue(any(min(a['active_turns']) == 3 for a in case['atoms']))

    def test_every_case_has_scoped_preservation_and_honest_evidence(self):
        for case in self.cases:
            dimensions = {atom['dimension'] for atom in case['atoms']}
            self.assertIn('preservation', dimensions)
            self.assertTrue(dimensions & {'evidence_honesty', 'runtime_evidence',
                                          'state_continuity'})
            self.assertGreaterEqual(len(dimensions), 5)
            self.assertEqual(len(case['provenance']['challenge_axes']), 5)
            self.assertIn('synthetic staged corrections', case['provenance']['feedback'])
            for atom in case['atoms']:
                self.assertNotRegex(atom['criterion'].lower(),
                                    r'(?:more|greater|higher) (?:polygon|element|object) count')
                self.assertTrue(atom['evidence']['required_artifacts'])

    def test_met_references_reuse_exact_licensed_bytes(self):
        originals = {a['id']: a for a in
                     read_json(ROOT.parent / 'assets' / 'manifest.json')['assets']}
        copied = {a['id']: a for a in self.assets if not a.get('authored_schematic')}
        self.assertEqual(set(copied), set(originals))
        for identifier, asset in copied.items():
            original = originals[identifier]
            self.assertEqual(asset['sha256'], original['sha256'])
            self.assertEqual(sha256(ROOT / 'assets' / asset['path']), original['sha256'])
            self.assertEqual((ROOT / 'assets' / asset['path']).read_bytes(),
                             (ROOT.parent / 'assets' / original['path']).read_bytes())
            self.assertEqual(asset['source'], original['source'])
            self.assertTrue(asset['is_public_domain'])
            self.assertIn('CC0', asset['license'])
            self.assertEqual((ROOT / 'assets' / asset['metadata']).read_bytes(),
                             (ROOT.parent / 'assets' / original['metadata']).read_bytes())

    def test_schematic_inputs_are_explicit_original_references(self):
        schematics = [a for a in self.assets if a.get('authored_schematic')]
        self.assertEqual(len(schematics), 6)
        for asset in schematics:
            self.assertEqual(asset['license'], 'CC0-1.0')
            self.assertEqual(asset['source'], 'MaintainAll authored schematic reference')
            image = ROOT / 'assets' / asset['path']
            raw = image.read_bytes()
            self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II', raw[16:24]), (960, 600))
            self.assertEqual(sha256(image), asset['sha256'])
            source = ROOT / 'assets' / asset['editable_source']
            self.assertEqual(sha256(source), asset['editable_source_sha256'])
            self.assertIn('Authored schematic reference', source.read_text())
            self.assertNotIn('real-session', asset['source'])

    def test_all_frozen_inputs_are_used_inside_suite_boundary(self):
        manifest_paths = {a['path'] for a in self.assets}
        used_paths = set()
        for case in self.cases:
            self.assertTrue(case['assets'])
            self.assertEqual(case['turns'][0]['attachments'],
                             [a['id'] for a in case['assets']])
            self.assertTrue(all(not t['attachments'] for t in case['turns'][1:]))
            for asset in case['assets']:
                path = (Path(case['_case_path']).parent / asset['path']).resolve()
                self.assertTrue(path.is_relative_to(ROOT))
                self.assertFalse(path.is_symlink())
                used_paths.add(path.name)
                self.assertEqual(sha256(path), asset['sha256'])
        self.assertEqual(used_paths, manifest_paths)

    def test_browser_tasks_require_native_motion_and_actual_capture_evidence(self):
        for case in self.cases:
            if 'browser_capture' not in case['capabilities']:
                continue
            for turn in case['turns']:
                artifacts = {a['path']: a for a in turn['artifacts']}
                self.assertEqual(artifacts['index.html']['kind'], 'editable')
                self.assertEqual((artifacts['desktop.png']['width'],
                                  artifacts['desktop.png']['height']), (1280, 800))
                self.assertEqual((artifacts['mobile.png']['width'],
                                  artifacts['mobile.png']['height']), (390, 844))
                for name in ('sequence-early.png', 'sequence-middle.png',
                             'sequence-late.png'):
                    self.assertEqual(artifacts[name]['kind'], 'preview')
                self.assertIn('Use actual browser captures.', turn['prompt'])
                self.assertIn('unexecuted behaviors explicitly untested', turn['prompt'])
            self.assertTrue(any(a['dimension'] in ('motion_continuity', 'state_continuity')
                                for a in case['atoms']))
            self.assertTrue(any('reduced motion' in r['quote'].lower()
                                for r in case['requirements']))

    def test_native_tasks_require_scene_source_and_counterfactual_renders(self):
        for case in self.cases:
            if 'blender' not in case['capabilities']:
                continue
            for turn in case['turns']:
                artifacts = {a['path']: a for a in turn['artifacts']}
                self.assertEqual(artifacts['scene.blend']['kind'], 'editable')
                self.assertEqual(artifacts['source.py']['kind'], 'editable')
                for name in ('a.png', 'b.png', 'side.png', 'parameter-probe.png'):
                    self.assertEqual((artifacts[name]['width'], artifacts[name]['height']),
                                     (640, 480))
                self.assertIn('independent saved-scene reopen', turn['prompt'])
                self.assertNotIn('svg', {a['format'] for a in turn['artifacts']})
            self.assertTrue(any(a['dimension'] == 'editability' and
                                'parameter-probe.png' in a['evidence']['required_artifacts']
                                for a in case['atoms']))

    def test_artifact_paths_remain_stable_and_bounded_across_corrections(self):
        for case in self.cases:
            expected = case['turns'][0]['artifacts']
            self.assertTrue(all(t['artifacts'] == expected for t in case['turns']))
            self.assertEqual(case['limits']['max_file_bytes'], 8 * 1024 * 1024)
            self.assertEqual(case['limits']['max_workspace_bytes'], 32 * 1024 * 1024)
            self.assertEqual(case['limits']['turn_seconds'], 600)
            actual = limits({'limits': case['limits']})
            self.assertEqual(actual['timeout_seconds'], 600)


if __name__ == '__main__':
    unittest.main()
