"""The report CLI accepts only sealed ratings within this run's private store."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import unittest

import test_runner
from skill_bench.cli import main
from skill_bench.review import export_review, freeze_review
from skill_bench.runner import run_experiment


class CliTests(unittest.TestCase):
    def setUp(self):
        fixture = test_runner.RunnerTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.temp = fixture.root
        self.run = fixture.root / 'run'
        run_experiment(self.run, execute=True, adapter=fixture.adapter)
        self.packet = self.temp / 'packet'
        packet = export_review(self.run, self.packet, seed=71)
        document = json.loads((self.packet / 'ratings-template.json').read_text())
        document['reviewer'].update(id='unknown-rating-fixture', **{'class': 'agent'})
        for row in document['ratings']:
            entry = next(e for e in packet['entries'] if e['id'] == row['entry'])
            turn = next(t for t in entry['turns'] if t['turn'] == row['turn'])
            item = turn['status_evidence']
            row.update(reason='Offline failure fixture: no valid image exists; quality is unknown.',
                       evidence=[{'path': item['path'], 'sha256': item['sha256']}])
        frozen = freeze_review(packet, document, self.run / 'reviews/ratings', media_root=self.packet)
        self.rating = Path(frozen['path'])

    def report(self, rating, name):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(['report', '--run', str(self.run), '--output', str(self.temp / name),
                         '--review-packet', str(self.packet), '--ratings', str(rating)])
        return code, output.getvalue(), error.getvalue()

    def test_official_frozen_record_exports_unknown_not_quality_pass(self):
        code, out, err = self.report(self.rating, 'valid')
        self.assertEqual(code, 0, err)
        data = json.loads((self.temp / 'valid/report.json').read_text())
        self.assertTrue(json.loads(out)['valid'])
        self.assertIsNone(data['automatic_quality_pass'])
        self.assertTrue(all(r['score'] == 'unverifiable' for r in data['ratings']))

    def test_lexical_parent_path_cannot_escape_frozen_store(self):
        external = self.temp / 'external.json'
        shutil.copyfile(self.rating, external)
        crafted = self.run / 'reviews/ratings/../../../external.json'
        code, _, error = self.report(crafted, 'escaped')
        self.assertEqual(code, 2, error)
        self.assertFalse((self.temp / 'escaped').exists())

    def test_frozen_rating_symlink_is_rejected_before_read(self):
        external = self.temp / 'external.json'
        shutil.copyfile(self.rating, external)
        link = self.run / 'reviews/ratings/symlink.json'
        link.symlink_to(external)
        code, _, error = self.report(link, 'linked')
        self.assertEqual(code, 2, error)
        self.assertFalse((self.temp / 'linked').exists())

    def test_hardlinked_rating_is_not_an_immutable_store_record(self):
        link = self.run / 'reviews/ratings/hardlink.json'
        link.hardlink_to(self.rating)
        code, _, error = self.report(link, 'hardlinked')
        self.assertEqual(code, 2, error)
        self.assertFalse((self.temp / 'hardlinked').exists())
