"""Public result packages preserve evidence and restore without model execution."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from skill_bench import cli, publication, report, result_packages as packages
from test_review import fixture


class ResultPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        run = self.root / 'run'
        run.mkdir()
        manifest = fixture(run)
        results = [json.loads(path.read_text()) for path in run.glob('trials/*/result.json')]
        self.bundle = self.root / 'public'
        report.export_report(report.build_report(manifest, results), self.bundle, media_root=run)
        self.archives = self.root / 'archives'
        self.archives.mkdir()
        self.archive = self.archives / 'example.zip'
        metadata = packages.pack_report(self.bundle, self.archive)
        self.entry = {'id': 'example', 'title': 'Example', 'path': 'example', 'suite_id': 'fixture',
                      **{key: metadata[key] for key in ('package', 'report_fingerprint', 'summary')}}
        self.entry['package']['url'] = 'https://example.invalid/releases/v1/example.zip'
        self.catalog = self.root / 'catalog.json'
        self.value = {'schema_version': 1, 'suites': [{'id': 'fixture', 'title': 'Fixture'}], 'reports': [self.entry]}
        self.save_catalog()

    def save_catalog(self):
        self.catalog.write_text(json.dumps(self.value))

    def restore(self, name='restored'):
        return packages.fetch_results(self.catalog, self.root / name, archives=self.archives)

    def rewrite_archive(self, transform):
        with zipfile.ZipFile(self.archive) as archive:
            members = [(info, archive.read(info)) for info in archive.infolist()]
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for info, data in transform(members):
                archive.writestr(info, data)
        data = self.archive.read_bytes()
        self.entry['package'].update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
        self.save_catalog()

    def test_deterministic_archive_omits_html_and_preserves_all_records_and_images(self):
        second = self.archives / 'second.zip'
        packages.pack_report(self.bundle, second)
        self.assertEqual(self.archive.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(self.archive) as archive:
            self.assertNotIn('index.html', archive.namelist())
        original = report.render_html
        renderer = lambda data: original(data) + '<!-- current renderer -->'
        with (patch('skill_bench.cli.run_experiment', side_effect=AssertionError('No generation')),
              patch('skill_bench.result_packages.render_html', side_effect=renderer),
              patch('skill_bench.report.render_html', side_effect=renderer)):
            proof = self.restore()
        self.assertEqual(proof['generation_calls'], 0)
        restored = self.root / 'restored/example'
        for source in self.bundle.rglob('*'):
            if source.is_file() and source.name != 'index.html':
                self.assertEqual((restored / source.relative_to(self.bundle)).read_bytes(), source.read_bytes())
        self.assertTrue((restored / 'index.html').read_text().endswith('<!-- current renderer -->'))

    def test_restored_results_publish_through_the_existing_suite_renderer(self):
        self.restore()
        proof = publication.publish_collection(self.root / 'restored', self.root / 'site')
        self.assertEqual(proof['generation_calls'], 0)
        self.assertTrue(publication.validate_public_site(self.root / 'site')['valid'])
        self.assertNotIn('data:image/', (self.root / 'site/timeline/index.html').read_text())

    def test_catalog_rejects_invalid_identity_summary_hash_size_and_location(self):
        original = json.loads(json.dumps(self.value))
        changes = [('path', '../outside'), ('path', 'a/b'), ('suite_id', 'unknown'),
                   ('report_fingerprint', 'short'), ('summary', {'trials': 0}),
                   ('package', {**self.entry['package'], 'size': True}),
                   ('package', {**self.entry['package'], 'size': packages.MAX_PACKAGE_BYTES + 1}),
                   ('package', {**self.entry['package'], 'sha256': 'short'})]
        changes.extend(('package', {**self.entry['package'], 'url': url}) for url in (
            'file:///tmp/example.zip', 'http://example.invalid/example.zip',
            'https://user:password@example.invalid/example.zip', 'https://example.invalid/x.zip?token=example',
            'https://example.invalid/%2e%2e.zip', 'https://example.invalid/x.zip#fragment'))
        for key, value in changes:
            with self.subTest(key=key, value=value):
                self.value = json.loads(json.dumps(original))
                self.value['reports'][0][key] = value
                self.save_catalog()
                with self.assertRaises(ValueError):
                    self.restore()
                self.assertFalse((self.root / 'restored').exists())

    def test_duplicate_catalog_fields_and_duplicate_report_identities_are_rejected(self):
        self.catalog.write_text('{"schema_version": 1, "schema_version": 1, "suites": [], "reports": []}')
        with self.assertRaises(ValueError):
            packages.load_catalog(self.catalog)
        self.value['reports'].append(dict(self.entry))
        self.save_catalog()
        with self.assertRaises(ValueError):
            packages.load_catalog(self.catalog)

    def test_hash_or_size_mismatch_never_leaves_a_partial_collection(self):
        original = self.archive.read_bytes()
        for data in (original[:-1], b'x' + original[1:]):
            with self.subTest(size=len(data)):
                self.archive.write_bytes(data)
                with self.assertRaisesRegex(ValueError, 'size or hash'):
                    self.restore()
                self.assertFalse((self.root / 'restored').exists())
                self.assertEqual(list(self.root.glob('.results-*')), [])

    def test_unsupported_members_are_rejected_even_with_a_valid_package_hash(self):
        original = self.archive.read_bytes()
        for name in ('../outside', '/absolute', 'media/../../escape', 'index.html', 'auth.json', 'media/' + 'a' * 64 + '.svg'):
            with self.subTest(name=name):
                self.archive.write_bytes(original)
                self.rewrite_archive(lambda members: [*members, (name, b'EXTRA')])
                with self.assertRaisesRegex(ValueError, 'unsupported member'):
                    self.restore()
        self.assertFalse((self.root / 'outside').exists())

    def test_archive_symlinks_duplicate_members_and_expansion_limits_are_rejected(self):
        original = self.archive.read_bytes()
        linked = zipfile.ZipInfo('media/' + 'a' * 64 + '.png')
        linked.create_system = 3
        linked.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.rewrite_archive(lambda members: [*members, (linked, b'../../outside')])
        with self.assertRaises(ValueError):
            self.restore()
        self.archive.write_bytes(original)
        with self.assertWarns(UserWarning):
            self.rewrite_archive(lambda members: [*members, members[0]])
        with self.assertRaises(ValueError):
            self.restore()
        self.archive.write_bytes(original)
        self.entry['package'].update(sha256=hashlib.sha256(original).hexdigest(), size=len(original))
        self.save_catalog()
        with patch.object(packages, 'MAX_MEMBERS', 1), self.assertRaisesRegex(ValueError, 'expanded'):
            self.restore()

    def test_summary_and_report_fingerprint_are_checked_against_restored_data(self):
        self.entry['summary']['ratings'] += 1
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, 'fingerprint or summary'):
            self.restore()
        self.entry['summary']['ratings'] -= 1
        self.entry['report_fingerprint'] = '0' * 64
        self.save_catalog()
        with self.assertRaisesRegex(ValueError, 'fingerprint or summary'):
            self.restore()

    def test_inner_media_hashes_are_checked_after_package_verification(self):
        self.rewrite_archive(lambda members: [(info, b'changed' if info.filename.startswith('media/') else data)
                                              for info, data in members])
        with self.assertRaisesRegex(ValueError, 'immutable inventory'):
            self.restore()

    def test_offline_files_and_destinations_cannot_be_links_or_overwritten(self):
        data = self.archive.read_bytes()
        self.archive.unlink()
        target = self.root / 'original.zip'
        target.write_bytes(data)
        self.archive.symlink_to(target)
        with self.assertRaises(ValueError):
            self.restore()
        self.archive.unlink()
        self.archive.write_bytes(data)
        self.restore()
        with self.assertRaisesRegex(ValueError, 'new destination'):
            self.restore()
        with self.assertRaisesRegex(ValueError, 'new destination'):
            packages.pack_report(self.bundle, self.archive)

    def test_download_uses_catalog_identity_and_redirects_require_https(self):
        with patch.object(packages, '_download', return_value=self.archive.read_bytes()) as download:
            packages.fetch_results(self.catalog, self.root / 'downloaded')
        download.assert_called_once_with(self.entry['package'])
        with self.assertRaises(ValueError):
            packages._HTTPSRedirect().redirect_request(None, None, 302, '', {}, 'http://example.invalid/data.zip')

    def test_cli_can_validate_restore_and_publish_without_generation(self):
        commands = [
            ['check-catalog', '--catalog', str(self.catalog)],
            ['fetch-results', '--catalog', str(self.catalog), '--archives', str(self.archives), '--output', str(self.root / 'cli')],
            ['check-reports', '--root', str(self.root / 'cli')],
            ['publish', '--root', str(self.root / 'cli'), '--output', str(self.root / 'cli-site')],
        ]
        with patch('skill_bench.cli.run_experiment', side_effect=AssertionError('No generation')):
            for command in commands:
                with self.subTest(command=command), redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(cli.main(command), 0)
                    self.assertEqual(json.loads(output.getvalue())['generation_calls'], 0)
