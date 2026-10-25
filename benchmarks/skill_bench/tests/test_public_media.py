"""Publication removes PNG metadata while preserving image and review identity."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from skill_bench import report
from test_review import fixture, pixel_png


def chunk(kind, content):
    return struct.pack('>I', len(content)) + kind + content + struct.pack('>I', zlib.crc32(kind + content) & 0xffffffff)


def annotated_png():
    clean = pixel_png(20)
    tags = [(b'tEXt', b'File\0/home/example-user/source.blend'),
            (b'zTXt', b'Comment\0\0' + zlib.compress(b'192.0.2.25')),
            (b'iTXt', b'Comment\0\0\0\0\0private render notes'),
            (b'eXIf', b'private camera metadata'), (b'tIME', bytes(7))]
    return clean[:33] + b''.join(chunk(kind, value) for kind, value in tags) + clean[33:]


class PublicMediaTests(unittest.TestCase):
    def setup_report(self, root):
        manifest = fixture(root)
        results = [json.loads(path.read_text()) for path in root.glob('trials/*/result.json')]
        value = report.build_report(manifest, results)
        item = value['media'][0]
        content = annotated_png()
        (root / 'trials' / item['trial_id'] / item['path']).write_bytes(content)
        item.update(sha256=hashlib.sha256(content).hexdigest(), size=len(content))
        original = {'path': 'media/' + item['sha256'] + '.png', 'sha256': item['sha256']}
        value['ratings'] = [{'score': 1, 'reason': 'Frozen review reason.', 'evidence': [dict(original)]}]
        value['pairs'] = [{'outcome_for_left': 'similar', 'reason': 'Frozen comparison.', 'evidence': [dict(original)]}]
        return value, original

    def test_export_removes_metadata_without_reencoding_or_rewriting_original_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value, original = self.setup_report(root)
            report.export_report(value, root / 'public', media_root=root)
            public = json.loads((root / 'public/report.json').read_text())
            item = public['media'][0]
            self.assertEqual((root / 'public' / item['export_path']).read_bytes(), pixel_png(20))
            self.assertEqual(item['source_sha256'], original['sha256'])
            self.assertEqual(item['transformation']['id'], 'png-metadata-removal-v1')
            self.assertEqual(set(item['transformation']['removed_chunks']), {'tEXt', 'zTXt', 'iTXt', 'eXIf', 'tIME'})
            for field in ('ratings', 'pairs'):
                evidence = public[field][0]['evidence'][0]
                self.assertEqual({k: evidence[k] for k in original}, original)
                self.assertEqual(evidence['public_path'], item['export_path'])
                self.assertEqual(evidence['public_sha256'], item['sha256'])
                self.assertEqual(public[field][0]['reason'], value[field][0]['reason'])
            self.assertEqual(value['ratings'][0]['evidence'][0], original)
            self.assertTrue(report.validate_public_bundle(root / 'public')['valid'])
            from skill_bench.publication import _site_projection
            projected = _site_projection(public)
            self.assertEqual(projected['ratings'][0]['evidence'][0]['public_path'], '../assets/' + item['sha256'] + '.png')
            self.assertEqual(projected['ratings'][0]['evidence'][0]['sha256'], original['sha256'])

    def test_public_bundle_rejects_invalid_derivative_provenance(self):
        from skill_bench.public_media import validate_derivation
        for changes in ({'source_sha256': 'invalid'}, {'source_size': 0}, {'transformation': {'id': 'not-an-export-transform'}}):
            item = {'source_sha256': 'a' * 64, 'sha256': 'b' * 64, 'size': 50, 'source_size': 100,
                    'transformation': {'id': 'png-metadata-removal-v1', 'removed_chunks': ['tEXt']}}
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'derivation'):
                validate_derivation({**item, **changes})

    def test_public_bundle_rejects_metadata_even_with_correct_seals_and_html(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value, _ = self.setup_report(root)
            report.export_report(value, root / 'public', media_root=root)
            public = json.loads((root / 'public/report.json').read_text())
            image = annotated_png()
            digest = hashlib.sha256(image).hexdigest()
            item = public['media'][0]
            (root / 'public' / item['export_path']).unlink()
            for key in ('source_sha256', 'source_size', 'transformation'):
                item.pop(key)
            item.update(sha256=digest, size=len(image), export_path='media/' + digest + '.png')
            (root / 'public' / item['export_path']).write_bytes(image)
            public['report_fingerprint'] = report.canonical_hash({k: v for k, v in public.items() if k != 'report_fingerprint'})
            (root / 'public/report.json').write_text(json.dumps(public))
            (root / 'public/index.html').write_text(report.render_html(public))
            with self.assertRaisesRegex(ValueError, 'PNG metadata'):
                report.validate_public_bundle(root / 'public')

    def test_clean_png_is_unchanged_and_cleanup_is_idempotent(self):
        from skill_bench.public_media import strip_png_metadata
        clean = pixel_png(20)
        self.assertEqual(strip_png_metadata(clean), (clean, []))
        sanitized, removed = strip_png_metadata(annotated_png())
        self.assertEqual(sanitized, clean)
        self.assertTrue(removed)
        self.assertEqual(strip_png_metadata(sanitized), (clean, []))
