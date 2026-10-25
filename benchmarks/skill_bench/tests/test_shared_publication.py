"""Published reports share original hashed images and keep embedding opt-in."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skill_bench import publication, report
from test_review import fixture


class SharedPublicationTests(unittest.TestCase):
    def collection(self, root):
        run = root/'run'
        run.mkdir()
        manifest = fixture(run)
        results = [json.loads(p.read_text()) for p in run.glob('trials/*/result.json')]
        collection = root/'collection'
        for name in ('first', 'second'):
            manifest['id'] = name
            report.export_report(report.build_report(manifest, results), collection/name, media_root=run)
        (collection/'reports.json').write_text(json.dumps({'schema_version':1,
            'reports':[{'id':name,'title':name,'path':name} for name in ('first','second')]}))
        return collection

    def test_default_publication_never_embeds_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collection = self.collection(root)
            with patch('skill_bench.publication.portable_report', wraps=publication.portable_report) as embedded:
                publication.publish_collection(collection, root/'site')
            self.assertFalse((root/'site/preview.html').exists())
            embedded.assert_not_called()
            for page in (root/'site').glob('*/index.html'):
                self.assertNotIn('data:image/', page.read_text())

    def test_reports_and_timeline_reference_one_copy_of_each_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collection = self.collection(root)
            publication.publish_collection(collection, root/'site')
            originals = json.loads((collection/'first/report.json').read_text())
            expected = {m['sha256'] for m in originals['media']}
            assets = list((root/'site/assets').glob('*'))
            self.assertEqual({p.stem for p in assets}, expected)
            self.assertEqual(len(assets), len(expected))
            for name in ('timeline',):
                public = json.loads((root/'site'/name/'report.json').read_text())
                self.assertTrue(all(m['export_path'].startswith('../assets/') for m in public['media']))
                self.assertTrue(all((root/'site'/name/m['export_path']).is_file() for m in public['media']))
                self.assertFalse((root/'site'/name/'media').exists())
            self.assertFalse((root/'site/first').exists())
            self.assertFalse((root/'site/second').exists())
            merged = json.loads((root/'site/timeline/report.json').read_text())
            self.assertEqual({e['id'] for e in merged['experiments']}, {'first', 'second'})
            self.assertTrue(publication.validate_public_site(root/'site')['valid'])

    def test_site_inventory_hashes_and_renderer_remain_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collection = self.collection(root)
            publication.publish_collection(collection, root/'site')
            site = root/'site'
            asset = next((site/'assets').glob('*'))
            original = asset.read_bytes()
            asset.write_bytes(b'broken')
            with self.assertRaises(ValueError):
                publication.validate_public_site(site)
            asset.write_bytes(original)
            (site/'auth.json').write_text('UNLISTED')
            with self.assertRaises(ValueError):
                publication.validate_public_site(site)
            (site/'auth.json').unlink()
            page = site/'timeline/index.html'
            page.write_text(page.read_text()+'<script>alert(1)</script>')
            with self.assertRaisesRegex(ValueError,'trusted.*renderer'):
                publication.validate_public_site(site)

    def test_portable_site_is_available_only_when_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collection = self.collection(root)
            publication.publish_collection(collection, root/'site')
            result = publication.portable_report(root/'site', root/'optional.html')
            self.assertEqual(result['generation_calls'],0)
            self.assertEqual(result['images'],2)
            self.assertIn('data:image/png;base64,',(root/'optional.html').read_text())
