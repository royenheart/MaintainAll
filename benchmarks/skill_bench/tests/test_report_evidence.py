"""Aligned report evidence keeps missing records and distinct reviews explicit."""
import shutil
import unittest

import test_report_view as view_tests


@unittest.skipUnless(shutil.which('node'), 'Node is required for evidence projection checks')
class ReportEvidenceTests(unittest.TestCase):
    project = view_tests.ReportViewTests.project

    def evidence(self, data, state='view.defaults()', turn=1, arms=('previous', 'candidate')):
        slots = ','.join("{arm:'" + arm + "',trial:source.trials.find(t=>t.id==='formal/" + arm + "1')}" for arm in arms)
        return self.project(data, "typeof view.evidenceRows==='function'?view.evidenceRows(" + state + ',[' + slots + '],' + str(turn) + ",source.case_contexts[0]||null):null")

    def media(self, arm, name, letter, turn=1, repeat=1):
        return {'trial_id': 'formal/' + arm + str(repeat), 'turn': turn, 'name': name,
                'kind': 'preview', 'sha256': letter * 64, 'export_path': 'media/' + letter * 64 + '.png'}

    def test_declared_outputs_align_by_name_and_extras_do_not_shift_rows(self):
        data = view_tests.browser_fixture()
        data['case_contexts'][0]['turns'][0]['artifacts'] = [
            {'path': 'selected.png', 'kind': 'preview', 'format': 'png'},
            {'path': 'other.png', 'kind': 'preview', 'format': 'png'},
            {'path': 'source.svg', 'kind': 'editable', 'format': 'svg'}]
        data['media'] += [self.media('previous', 'other.png', 'c'),
                          self.media('previous', 'additional-preview', 'd'),
                          self.media('candidate', 'selected.png', 'e', repeat=2),
                          self.media('candidate', 'other.png', 'f', turn=2)]
        actual = self.evidence(data)
        self.assertIsNotNone(actual, 'Evidence must project matched artifact rows before rendering')
        self.assertEqual([row['name'] for row in actual['outputs']], ['selected.png', 'other.png'])
        self.assertEqual([[len(cell['media']) for cell in row['cells']] for row in actual['outputs']], [[0, 1], [1, 0]])
        self.assertEqual([[item['name'] for item in cell['media']] for cell in actual['extras']], [['additional-preview'], []])

    def test_multiple_images_for_one_output_are_preserved_without_overwriting(self):
        data = view_tests.browser_fixture()
        data['media'].append(self.media('candidate', 'selected.png', 'c'))
        actual = self.evidence(data)
        self.assertIsNotNone(actual)
        self.assertEqual([m['sha256'] for m in actual['outputs'][0]['cells'][1]['media']], ['a' * 64, 'c' * 64])

    def test_atoms_align_with_applicability_missing_reviews_and_multiple_reviewers(self):
        data = view_tests.browser_fixture()
        context = data['case_contexts'][0]
        context['atoms'] += [dict(context['atoms'][0], id='unreviewed'),
                             dict(context['atoms'][0], id='later', active_turns=[2])]
        rating = next(r for r in data['ratings'] if r['trial_id'] == 'formal/candidate1')
        data['ratings'] += [dict(rating, score=0, judge={**rating['judge'], 'id': 'second'}, review_version=2),
                            dict(rating, atom='layout', turn=2, score=1),
                            dict(rating, atom='layout', trial_id='formal/candidate2', repeat=2, score=0)]
        actual = self.evidence(data)
        self.assertIsNotNone(actual)
        self.assertEqual([row['id'] for row in actual['atoms']], ['layout', 'unreviewed'])
        self.assertEqual([[len(cell['records']) for cell in row['cells']] for row in actual['atoms']], [[1, 2], [0, 0]])
        self.assertEqual([r['score'] for r in actual['atoms'][0]['cells'][1]['records']], [2, 0])
        filtered = self.evidence(data, "{...view.defaults(),judge:'agent:second',review_version:'2'}")
        self.assertEqual([len(cell['records']) for cell in filtered['atoms'][0]['cells']], [0, 1])

    def test_legacy_reports_use_available_names_and_do_not_invent_scoring_rules(self):
        data = view_tests.browser_fixture()
        data['case_contexts'] = []
        data['media'].append(self.media('previous', 'additional-preview', 'c'))
        actual = self.evidence(data)
        self.assertIsNotNone(actual)
        self.assertEqual([row['name'] for row in actual['outputs']], ['selected.png'])
        self.assertEqual(actual['atoms'][0]['id'], 'layout')
        self.assertIsNone(actual['atoms'][0]['definition'])

    def test_single_version_and_private_cases_do_not_borrow_other_outputs(self):
        data = view_tests.browser_fixture()
        actual = self.evidence(data, "{...view.defaults(),skill:'candidate'}", arms=('candidate',))
        self.assertIsNotNone(actual)
        self.assertEqual(len(actual['outputs'][0]['cells']), 1)
        self.assertEqual(len(actual['atoms'][0]['cells']), 1)
        data['case_contexts'][0] = {'visibility': 'private'}
        private = self.evidence(data)
        self.assertEqual(private['outputs'], [])
        self.assertTrue(all(not cell['media'] for cell in private['extras']))
