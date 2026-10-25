"""Manual generation and credential-free publication remain separate."""
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from skill_bench import cli, report
from test_report_view import browser_fixture


class ManualPublicationTests(unittest.TestCase):
    maxDiff = 1200
    def collection(self, root):
        reports = root / 'reports'
        reports.mkdir()
        report.export_report(report.build_report({'id': 'manual', 'arms': [], 'cases': [],
            'schedule': [], 'model': 'none', 'effort': 'none', 'backend': 'offline'}, []), reports / 'example')
        (reports / 'reports.json').write_text(json.dumps({'schema_version': 1,
            'reports': [{'id': 'example', 'title': 'Manual evaluation', 'path': 'example'}]}))
        return reports

    def test_ci_has_no_model_request_or_authenticated_runner(self):
        workflow = (Path(__file__).resolve().parents[3] / '.github/workflows/skill-benchmark.yml').read_text()
        self.assertNotIn('\n  request:', workflow)
        self.assertNotIn('trusted_sha:', workflow)
        self.assertNotIn('make_push_request', workflow)
        self.assertNotIn('self-hosted', workflow)
        self.assertNotIn('pull_request_target', workflow)
        self.assertNotIn('secrets.', workflow)
        self.assertNotIn('skill-bench run', workflow)
        self.assertIn('persist-credentials: false', workflow)
        actions = re.findall(r'uses:\s*([^\s#]+)', workflow)
        self.assertTrue(actions)
        self.assertTrue(all(re.fullmatch(r'[A-Za-z0-9_/-]+@[0-9a-f]{40}', action) for action in actions))
        self.assertIn('skill-bench fetch-results', workflow)
        self.assertIn('skill-bench publish', workflow)
        self.assertIn('runs-on: ubuntu-latest', workflow)

    def test_remote_generation_commands_are_unavailable(self):
        for args in (['track', 'drain', '--state-root', '/unused', '--execute'], ['worker', '--execute']):
            with self.subTest(args=args):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    cli.parser().parse_args(args)
                self.assertEqual(error.exception.code, 2)
        self.assertFalse(cli.parser().parse_args(['run', '--run', '/unused']).execute)

    def test_report_interface_is_english_and_uses_readable_labels(self):
        document = report.render_html(browser_fixture())
        self.assertIn('lang="en"', document)
        self.assertNotRegex(document, r'[\u4e00-\u9fff]')
        for label in ('Completed runs', 'Failed or stopped runs', 'Recorded / planned turns',
                      'Better', 'Similar', 'Worse', 'Not enough evidence'):
            self.assertIn(label, document)

    def test_checked_publication_never_starts_generation_or_copies_unlisted_files(self):
        from skill_bench import publication
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            collection = self.collection(root)
            (collection / 'private-session.jsonl').write_text('PRIVATE')
            (collection / 'auth.json').write_text('SECRET')
            with patch('skill_bench.cli.run_experiment', side_effect=AssertionError('No generation')):
                checked = publication.validate_collection(collection)
                published = publication.publish_collection(collection, root / 'site')
            self.assertEqual(checked['reports'], 1)
            self.assertEqual(published['generation_calls'], 0)
            self.assertTrue(publication.validate_public_site(root / 'site')['valid'])
            self.assertNotIn('PRIVATE', (root / 'site/index.html').read_text())
            self.assertFalse((root / 'site/auth.json').exists())
            self.assertFalse((root / 'site/private-session.jsonl').exists())

    def test_changed_bundle_or_unsafe_catalog_fails_before_publication(self):
        from skill_bench import publication
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            collection = self.collection(root)
            catalog = collection / 'reports.json'
            original = json.loads(catalog.read_text())
            for path in ('../private', '/absolute', 'https://example.invalid', 'example/../example'):
                document = json.loads(json.dumps(original))
                document['reports'][0]['path'] = path
                catalog.write_text(json.dumps(document))
                with self.subTest(path=path), self.assertRaises(ValueError):
                    publication.publish_collection(collection, root / 'unsafe')
                self.assertFalse((root / 'unsafe').exists())
            catalog.write_text(json.dumps(original))
            (collection / 'example/index.html').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'trusted escaped renderer'):
                publication.publish_collection(collection, root / 'changed')
            self.assertFalse((root / 'changed').exists())

    def test_linked_bundle_and_existing_destination_are_rejected(self):
        from skill_bench import publication
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            collection = self.collection(root)
            (collection / 'linked').symlink_to(collection / 'example', target_is_directory=True)
            (collection / 'reports.json').write_text(json.dumps({'schema_version': 1,
                'reports': [{'id': 'linked', 'title': 'Linked', 'path': 'linked'}]}))
            with self.assertRaises(ValueError):
                publication.validate_collection(collection)
            (collection / 'reports.json').write_text(json.dumps({'schema_version': 1,
                'reports': [{'id': 'example', 'title': 'Manual', 'path': 'example'}]}))
            site = root / 'site'
            site.mkdir()
            (site / 'sentinel').write_text('keep')
            with self.assertRaises(ValueError):
                publication.publish_collection(collection, site)
            self.assertEqual((site / 'sentinel').read_text(), 'keep')

    def test_default_site_keeps_timeline_without_creating_portable_copies(self):
        from skill_bench import publication
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            collection = self.collection(root)
            with patch('skill_bench.publication.portable_report', side_effect=AssertionError('Embedding is opt-in')):
                result = publication.publish_collection(collection, root/'site')
            self.assertFalse(result['embedded_images'])
            self.assertTrue((root/'site/timeline/report.json').is_file())
            manifest = json.loads((root/'site/publication.json').read_text())
            self.assertEqual([(e['path'], e['role']) for e in manifest['reports']], [('timeline', 'history')])
            self.assertFalse((root/'site/example').exists())
            self.assertNotIn('class="suite-reports"', (root/'site/timeline/index.html').read_text())
            self.assertFalse((root/'site/preview-example.html').exists())
            self.assertNotIn('href="preview.html"', (root/'site/index.html').read_text())

    def test_unlisted_framework_checks_never_enter_suite_history(self):
        from skill_bench import publication
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            collection = self.collection(root)
            for name in ('development', 'compatibility'):
                report.export_report(report.build_report({'id': 'framework-' + name,
                    'arms': [], 'cases': [], 'schedule': []}, []), collection / name)
            publication.publish_collection(collection, root / 'site')
            history = json.loads((root / 'site/timeline/report.json').read_text())
            self.assertEqual([e['id'] for e in history['experiments']], ['manual'])
            for name in ('development', 'compatibility'):
                self.assertFalse((root / 'site' / name).exists())
                self.assertTrue((collection / name / 'report.json').is_file())

    def test_repository_catalog_summaries_preserve_formal_evaluations(self):
        from skill_bench.result_packages import DEFAULT_CATALOG, load_catalog
        repo = Path(__file__).resolve().parents[3]
        catalog = load_catalog(repo / DEFAULT_CATALOG)
        internal = {'20261009-development-harbor-v1', '20261009-compat-local-v2'}
        for entry in catalog['reports']:
            self.assertFalse(internal.intersection(entry['summary']['experiments']))
        entry = next(entry for entry in catalog['reports'] if entry['id'] == 'formal')
        self.assertEqual(entry['title'], 'Formal comparison')
        self.assertEqual(entry['summary']['experiments'], ['20261009-formal-harbor-v2'])
        self.assertEqual(entry['summary']['trials'], 18)
        self.assertEqual(entry['summary']['ratings'], 322)
