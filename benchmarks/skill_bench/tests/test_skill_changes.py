"""Commit selection and diffs come from recorded versions and frozen bytes."""
import json
from pathlib import Path
import tempfile
import unittest

from skill_bench import report
from skill_bench.experiment import freeze_skill
import test_report_view as viewer_tests
browser_fixture = viewer_tests.browser_fixture
from test_review import fixture


class SkillChangeTests(unittest.TestCase):
    def inputs(self, root):
        manifest = fixture(root)
        for arm, text in [('previous', 'Original instruction\n'), ('candidate', 'Updated instruction\n')]:
            source = root / ('input-' + arm)
            source.mkdir()
            (source / 'SKILL.md').write_text(text)
            (source / 'unchanged.md').write_text('Shared rule\n')
            if arm == 'previous': (source / 'removed.md').write_text('Old method\n')
            else: (source / 'added.md').write_text('New method\n')
            identity = freeze_skill(source, root / 'skills' / arm)
            next(a for a in manifest['arms'] if a['id'] == arm).update(identity, skill_snapshot='skills/' + arm)
        results = [json.loads(p.read_text()) for p in root.glob('trials/*/result.json')]
        return manifest, results

    def test_report_exposes_exact_frozen_changes_without_calling_a_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, results = self.inputs(root)
            # A later checkout edit must not change the evaluated source diff.
            (root / 'input-candidate/SKILL.md').write_text('Uncommitted later edit')
            public = report.build_report(manifest, results, skill_root=root)
            change = public['experiments'][0]['skill_changes']
            self.assertIn('-Original instruction', change['patch'])
            self.assertIn('+Updated instruction', change['patch'])
            self.assertNotIn('Uncommitted', change['patch'])
            self.assertEqual({f['path']: f['status'] for f in change['files']},
                             {'SKILL.md': 'modified', 'added.md': 'added', 'removed.md': 'deleted'})
            self.assertEqual(public['experiments'][0]['commit_provenance'], {})
            self.assertTrue(report.export_report(public, root / 'public', media_root=root)['sanitized'])
            self.assertTrue(report.validate_public_bundle(root / 'public')['valid'])

    def test_tampered_snapshot_fails_instead_of_showing_a_false_diff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, results = self.inputs(root)
            (root / 'skills/candidate/SKILL.md').write_text('Tampered')
            with self.assertRaisesRegex(ValueError, 'Frozen skill'):
                report.build_report(manifest, results, skill_root=root)

    def test_same_frozen_data_generates_identical_patch_and_report_html(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, results = self.inputs(root)
            for name in ('first','second'):
                public = report.build_report(manifest, results, skill_root=root)
                report.export_report(public, root / name, media_root=root)
            for name in ('report.json','index.html'):
                self.assertEqual((root / 'first' / name).read_bytes(), (root / 'second' / name).read_bytes())

    def test_private_binary_and_oversize_files_have_explicit_omission_reasons(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, results = self.inputs(root)
            source = root / 'input-candidate'
            (source / 'private.md').write_text('authorization: bearer hidden-value')
            (source / 'binary.dat').write_bytes(b'\x00binary')
            (source / 'large.md').write_text('x' * (256 * 1024 + 1))
            import shutil
            shutil.rmtree(root / 'skills/candidate')
            next(a for a in manifest['arms'] if a['id'] == 'candidate').update(freeze_skill(source, root / 'skills/candidate'))
            changes = report.build_report(manifest, results, skill_root=root)['experiments'][0]['skill_changes']
            reasons = {f['path']: f['omitted_reason'] for f in changes['files'] if f['omitted_reason']}
            self.assertEqual(reasons, {'private.md':'private-content', 'binary.dat':'binary', 'large.md':'size-limit'})
            self.assertNotIn('hidden-value', json.dumps(changes))
            self.assertNotIn('authorization', changes['patch'])

    def test_patch_tampering_is_rejected_by_public_bundle_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, results = self.inputs(root)
            public = report.build_report(manifest, results, skill_root=root)
            report.export_report(public, root / 'public', media_root=root)
            path = root / 'public/report.json'
            public = json.loads(path.read_text())
            public['experiments'][0]['skill_changes']['patch'] += '+invented\n'
            from skill_bench.review import canonical_hash
            public['report_fingerprint'] = canonical_hash({k:v for k,v in public.items() if k != 'report_fingerprint'})
            path.write_text(json.dumps(public))
            (path.parent / 'index.html').write_text(report.render_html(public))
            with self.assertRaisesRegex(ValueError, 'patch|diff'):
                report.validate_public_bundle(path.parent)


class CommitControlTests(unittest.TestCase):
    project = viewer_tests.ReportViewTests.project

    def fixture(self):
        data = browser_fixture()
        for i, exp in enumerate(data['experiments']):
            exp['commit_provenance'] = {'candidate_sha': str(i+1)*40, 'previous_sha':'0'*40}
        return data

    def test_primary_controls_use_tested_commit_ids(self):
        page = report.render_html(self.fixture())
        self.assertIn('id="candidate-commit-select"', page)
        self.assertIn('id="baseline-commit-select"', page)
        self.assertIn('id="skill-diff"', page)
        self.assertIn('Diff2Html', page)

    def test_commit_selection_resolves_only_recorded_pairs_and_preserves_runs(self):
        data = self.fixture()
        chosen = self.project(data, "view.chooseVersions(view.defaults(),'commit:'+'1'.repeat(40),'commit:'+'0'.repeat(40))")
        self.assertEqual(chosen['experiment'], 'development')
        self.assertEqual(chosen['baseline'], 'previous')
        options = self.project(data, 'view.versionOptions(view.defaults())')
        self.assertEqual({c['id'] for c in options['candidates']}, {'commit:'+'1'*40, 'commit:'+'2'*40})
        self.assertEqual(self.project(data, "view.chooseVersions(view.defaults(),'commit:'+'1'.repeat(40),'commit:'+'9'.repeat(40))"), None)

    def test_same_commit_multiple_runs_remain_individual(self):
        data = self.fixture()
        data['experiments'][1]['commit_provenance']['candidate_sha'] = '1'*40
        actual = self.project(data, 'view.versionOptions(view.defaults())')
        self.assertEqual(len(actual['candidates']), 1)
        self.assertEqual(set(actual['runs']), {'development', 'formal'})

    def test_unrecorded_commit_is_never_replaced_by_an_upload_hash(self):
        options = self.project(browser_fixture(), 'view.versionOptions(view.defaults())')
        self.assertTrue(all(c['commit'] is None and c['id'].startswith('snapshot:') for c in options['candidates']))

    def test_version_labels_include_full_identity_for_every_experiment(self):
        data = self.fixture()
        versions = self.project(data, "['development','formal'].map(id=>view.versionInfo(id,'candidate'))")
        self.assertEqual([v['label'] for v in versions], ['Commit ' + '1'*40, 'Commit ' + '2'*40])

    def test_snapshot_labels_keep_full_hash_and_missing_identity_is_explicit(self):
        data = browser_fixture()
        data['experiments'][0]['arms'] = [{'id':'previous','skill_hash':'a'*64}]
        snapshot = self.project(data, "view.versionInfo('development','previous')")
        self.assertEqual(snapshot['label'], 'Snapshot ' + 'a'*64)
        data['cohorts'] = []
        missing = self.project(data, "view.versionInfo('formal','candidate')")
        self.assertEqual(missing['label'], 'Version identity not recorded')

    def test_no_redundant_role_only_comparison_selector_remains(self):
        page = report.render_html(self.fixture())
        self.assertNotIn('id="baseline-select"', page)
        self.assertNotIn('Previous skill', page)
        self.assertIn('translate="no"', page)
