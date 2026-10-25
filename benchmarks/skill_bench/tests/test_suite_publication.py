"""Independent benchmark suites share navigation and bytes, never results."""
import copy
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skill_bench import cli, publication, report
from test_review import fixture


class SuitePublicationTests(unittest.TestCase):
    def collection(self, root):
        run = root / 'run'
        run.mkdir()
        manifest = fixture(run)
        results = [json.loads(p.read_text()) for p in run.glob('trials/*/result.json')]
        manifest['id'] = 'same-experiment-id'
        collection = root / 'collection'
        report.export_report(report.build_report(manifest, results), collection / 'art', media_root=run)
        changed = copy.deepcopy(results)
        changed[0]['status'] = 'failed'
        manifest['cases'][0]['atoms'][0]['dimension'] = 'correctness'
        report.export_report(report.build_report(manifest, changed), collection / 'coding', media_root=run)
        catalog = {'schema_version': 2,
            'suites': [{'id': 'art-creation', 'title': 'Art creation'},
                       {'id': 'code-review', 'title': 'Code review'}],
            'reports': [{'id': 'art', 'title': 'Art comparison', 'path': 'art', 'suite_id': 'art-creation'},
                        {'id': 'coding', 'title': 'Review comparison', 'path': 'coding', 'suite_id': 'code-review'}]}
        (collection / 'reports.json').write_text(json.dumps(catalog))
        return collection

    def test_histories_are_isolated_even_with_overlapping_experiment_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collection = self.collection(root)
            try:
                checked = publication.publish_collection(collection, root / 'site')
            except ValueError as error:
                self.fail('Independent benchmark suite publication was rejected: ' + str(error))
            self.assertEqual(checked['suites'], 2)
            manifest = json.loads((root / 'site/publication.json').read_text())
            for suite in manifest['suites']:
                history = json.loads((root / 'site' / suite['path'] / 'report.json').read_text())
                self.assertEqual(len(history['trials']), 2)
                self.assertEqual(history['publication']['suite']['id'], suite['id'])
                self.assertEqual({c['dimension'] for c in history['case_contexts'][0]['atoms']},
                                 {'construction' if suite['id'] == 'art-creation' else 'correctness'})
                self.assertEqual(sum(t['status'] == 'failed' for t in history['trials']),
                                 0 if suite['id'] == 'art-creation' else 1)
            self.assertEqual(len(list((root / 'site/assets').iterdir())), 2)
            self.assertTrue(publication.validate_public_site(root / 'site')['valid'])

    def test_suite_navigation_links_resolve_and_current_suite_is_identified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publication.publish_collection(self.collection(root), root / 'site')
            manifest = json.loads((root / 'site/publication.json').read_text())
            for entry in manifest['reports']:
                page = (root / 'site' / entry['path'] / 'index.html').read_text()
                self.assertIn('aria-label="Benchmark suites"', page)
                self.assertIn('aria-current="page"', page)
                self.assertIn('Art creation', page)
                self.assertIn('Code review', page)
                public = json.loads((root / 'site' / entry['path'] / 'report.json').read_text())
                for item in public['publication']['suites'] + public['publication']['reports']:
                    self.assertTrue((root / 'site' / item['path'] / 'index.html').is_file())
                self.assertIn(public['publication']['suite']['title'] + ' benchmark', page)

    def test_bad_suite_assignments_and_reserved_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collection = self.collection(root)
            path = collection / 'reports.json'
            original = json.loads(path.read_text())
            for change in ('unknown', 'missing', 'duplicate', 'traversal', 'reserved'):
                value = copy.deepcopy(original)
                if change == 'unknown': value['reports'][0]['suite_id'] = 'unknown'
                if change == 'missing': value['reports'][0].pop('suite_id')
                if change == 'duplicate': value['suites'].append(value['suites'][0])
                if change == 'traversal': value['suites'][0]['id'] = '../private'
                if change == 'reserved': value['reports'][0]['id'] = 'suite-code-review'
                path.write_text(json.dumps(value))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    publication.publish_collection(collection, root / 'bad')
                self.assertFalse((root / 'bad').exists())

    def test_standalone_renderer_has_no_art_only_title(self):
        page = report.render_html(report.build_report({'id': 'generic', 'arms': [], 'cases': [], 'schedule': []}, []))
        self.assertIn('<title>Skill benchmark report</title>', page)
        self.assertNotIn('Art creation skill evaluation', page)

    def test_commit_plan_requires_explicit_skill_selection(self):
        arguments = ['plan', '--suite', '/unused/suite.json', '--repo', '/unused/repo',
            '--previous-ref', 'HEAD~1', '--candidate-ref', 'HEAD', '--output', '/unused/run']
        self.assertIsNone(cli.parser().parse_args(arguments).skill_path)
        errors = io.StringIO()
        with redirect_stderr(errors), patch('skill_bench.manual.committed_skills') as snapshot:
            self.assertEqual(cli.main(arguments), 2)
        snapshot.assert_not_called()
        self.assertIn('--skill-path', errors.getvalue())

    def test_portable_export_requires_selection_for_multiple_suites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publication.publish_collection(self.collection(root), root / 'site')
            with self.assertRaisesRegex(ValueError, 'Choose a benchmark suite'):
                publication.portable_report(root / 'site', root / 'ambiguous.html')
            self.assertFalse((root / 'ambiguous.html').exists())
            result = publication.portable_report(root / 'site', root / 'coding.html', suite_id='code-review')
            self.assertEqual(result['generation_calls'], 0)
            self.assertIn('<title>Code review benchmark</title>', (root / 'coding.html').read_text())

    def test_site_validator_rejects_cross_suite_navigation_assignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publication.publish_collection(self.collection(root), root / 'site')
            path = root / 'site/timeline/report.json'
            public = json.loads(path.read_text())
            public['publication']['suite'] = {'id': 'code-review', 'title': 'Code review'}
            public['report_fingerprint'] = publication.canonical_hash({k:v for k,v in public.items() if k != 'report_fingerprint'})
            path.write_text(json.dumps(public))
            (path.parent / 'index.html').write_text(report.render_html(public))
            manifest = json.loads((root / 'site/publication.json').read_text())
            next(e for e in manifest['reports'] if e['path'] == 'timeline')['report_fingerprint'] = public['report_fingerprint']
            (root / 'site/publication.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'suite|navigation'):
                publication.validate_public_site(root / 'site')
