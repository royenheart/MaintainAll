"""Manual commit identity, append-only history and portable image evidence."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import io

from skill_bench import report, publication
import test_report_view as viewer_tests
browser_fixture = viewer_tests.browser_fixture
from test_review import fixture


class CommitHistoryTests(unittest.TestCase):
    def test_git_snapshots_freeze_commits_instead_of_dirty_worktree(self):
        from skill_bench.manual import committed_skills
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / 'repo'
            repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
            git('init', '-q')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'user.name', 'Test')
            skill = repo / 'skills/art-creation'
            skill.mkdir(parents=True)
            (skill / 'SKILL.md').write_text('old')
            git('add', '.')
            git('commit', '-qm', 'old')
            previous = git('rev-parse', 'HEAD')
            (skill / 'SKILL.md').write_text('new')
            git('commit', '-qam', 'new')
            candidate = git('rev-parse', 'HEAD')
            (skill / 'SKILL.md').write_text('uncommitted')
            with committed_skills(repo, previous, candidate) as (sources, provenance):
                self.assertEqual((sources['previous'] / 'SKILL.md').read_text(), 'old')
                self.assertEqual((sources['candidate'] / 'SKILL.md').read_text(), 'new')
                self.assertEqual(provenance['candidate_sha'], candidate)
                self.assertEqual(provenance['previous_sha'], previous)
                self.assertEqual(provenance['source'], 'local-manual')
                self.assertIn(previous, provenance['candidate_parents'])
                self.assertIsInstance(provenance['candidate_committed_epoch'], int)
                self.assertNotIn('source_run_id', provenance)
            from skill_bench.cli import main
            from test_runner import RunnerTests
            harness = RunnerTests()
            harness.setUp()
            self.addCleanup(harness.doCleanups)
            with patch('skill_bench.experiment.backend', return_value=harness.adapter), redirect_stdout(io.StringIO()):
                self.assertEqual(main(['plan', '--suite', str(harness.root/'suite.json'),
                    '--repo', str(repo), '--previous-ref', previous, '--candidate-ref', candidate,
                    '--skill-path', 'skills/art-creation',
                    '--output', str(root/'cli-plan'), '--max-calls', '4']), 0)
            from skill_bench.experiment import load_experiment
            planned = load_experiment(root/'cli-plan')
            self.assertEqual(planned['commit_provenance']['candidate_sha'], candidate)
            self.assertEqual((root/'cli-plan/skills/candidate/SKILL.md').read_text(), 'new')
            self.assertEqual(harness.adapter.calls, 0)
            with self.assertRaises(ValueError):
                with committed_skills(repo, '--help', candidate):
                    pass
            with self.assertRaises(ValueError):
                with committed_skills(repo, previous, candidate, skill_path='../private'):
                    pass

    def test_manual_provenance_is_sealed_by_existing_plan(self):
        from test_runner import RunnerTests
        from skill_bench.experiment import prepare_experiment, load_experiment
        harness = RunnerTests()
        harness.setUp()
        self.addCleanup(harness.doCleanups)
        provenance = {'source': 'local-manual', 'candidate_sha': 'a'*40,
            'previous_sha': 'b'*40, 'candidate_committed_epoch': 123,
            'candidate_parents': ['b'*40], 'protocol_id': 'manual-paired-v1'}
        with patch('skill_bench.experiment.backend', return_value=harness.adapter):
            manifest = prepare_experiment(harness.root/'suite.json', harness.root/'manual',
                arms={'none': None}, max_calls=2, commit_provenance=provenance)
        self.assertEqual(load_experiment(harness.root/'manual')['commit_provenance'], provenance)
        self.assertEqual(report._experiment_metadata(manifest)['commit_provenance'], provenance)

    def test_combined_history_keeps_old_images_and_deduplicates_existing_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(p.read_text()) for p in root.glob('trials/*/result.json')]
            first = report.build_report(manifest, results)
            manifest['id'] = 'second'
            second = report.build_report(manifest, results)
            report.export_report(first, root/'first-public', media_root=root)
            report.export_report(report.merge_reports([first, second]), root/'merged-public', media_root=root)
            combined, roots = publication.combine_public_reports([root/'first-public', root/'merged-public'])
            report.export_report(combined, root/'combined', public_roots=roots)
            public = json.loads((root/'combined/report.json').read_text())
            self.assertEqual(len(public['trials']), len(first['trials']) + len(second['trials']))
            self.assertEqual({m['experiment'] for m in public['media']}, {first['experiment'], 'second'})
            self.assertTrue(report.validate_public_bundle(root/'combined')['valid'])
            portable = publication.portable_report(root/'combined', root/'portable.html')
            self.assertEqual(portable['generation_calls'], 0)
            text = (root/'portable.html').read_text()
            self.assertIn('data:image/png;base64,', text)
            self.assertIn("img-src &#x27;self&#x27; data:", text)
            self.assertNotIn(str(root), text)
            with self.assertRaises(ValueError):
                publication.portable_report(root/'combined', root/'portable.html')

    def test_duplicate_experiment_with_changed_trial_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(p.read_text()) for p in root.glob('trials/*/result.json')]
            first = report.build_report(manifest, results)
            report.export_report(first, root/'first', media_root=root)
            first['trials'][0]['status'] = 'failed'
            report.export_report(first, root/'changed', media_root=root)
            with self.assertRaisesRegex(ValueError, 'Conflicting.*trial'):
                publication.combine_public_reports([root/'first', root/'changed'])

    def test_report_cli_keeps_images_when_reusing_already_merged_history(self):
        from skill_bench.cli import main
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(p.read_text()) for p in root.glob('trials/*/result.json')]
            first = report.build_report(manifest, results)
            manifest['id'] = 'second'
            second = report.build_report(manifest, results)
            report.export_report(first, root/'past/original', media_root=root)
            report.export_report(report.merge_reports([first, second]), root/'past/merged', media_root=root)
            manifest['id'] = 'third'
            with patch('skill_bench.cli.load_experiment', return_value=manifest), \
                    patch('skill_bench.cli.load_results', return_value=results), \
                    patch('skill_bench.cli.read_events', return_value=[]), redirect_stdout(io.StringIO()):
                self.assertEqual(main(['report', '--run', str(root), '--history', str(root/'past'),
                    '--output', str(root/'final')]), 0)
            public = json.loads((root/'final/report.json').read_text())
            self.assertEqual(len(public['trials']), 3*len(first['trials']))
            self.assertEqual({m['experiment'] for m in public['media']}, {first['experiment'], 'second', 'third'})


class CommitProjectionTests(unittest.TestCase):
    project = viewer_tests.ReportViewTests.project
    def test_commit_axis_allows_skill_changes_but_splits_other_conditions(self):
        data = browser_fixture()
        for index, exp in enumerate(data['experiments']):
            exp['commit_provenance'] = {'candidate_sha': str(index+1)*40,
                'previous_sha': '0'*40, 'candidate_committed_epoch': 100+index}
        for cohort in data['cohorts']:
            if cohort['id'].startswith('formal-'):
                cohort['skill_hash'] = 'improved-skill'
        actual = self.project(data, 'view.commitSeries({...view.defaults(),skill:"candidate"})')
        self.assertEqual(len(actual), 1)
        self.assertEqual([r['commit'] for r in actual[0]['rows']], ['1'*40, '2'*40])
        self.assertEqual(actual[0]['rows'][1]['score_counts']['unverifiable'], 1)
        next(c for c in data['cohorts'] if c['id']=='formal-candidate')['generation_runtime_fingerprint'] = 'changed'
        self.assertEqual(len(self.project(data, 'view.commitSeries({...view.defaults(),skill:"candidate"})')), 2)

    def test_commit_condition_includes_judge_budget_task_and_seed(self):
        for field in ('judge', 'execution_policy_fingerprint', 'case_fingerprint', 'trial_order_seed'):
            data = browser_fixture()
            for index, exp in enumerate(data['experiments']):
                exp['commit_provenance'] = {'candidate_sha': str(index+1)*40, 'candidate_committed_epoch':100+index}
            cohort = next(c for c in data['cohorts'] if c['id']=='formal-candidate')
            if field == 'judge':
                cohort[field] = {**cohort[field], 'id': 'new-judge'}
            else:
                cohort[field] = 'changed'
            with self.subTest(field=field):
                self.assertEqual(len(self.project(data, 'view.commitSeries({...view.defaults(),skill:"candidate"})')), 2)

    def test_unknown_commits_do_not_become_upload_commit_points(self):
        self.assertEqual(self.project(browser_fixture(), 'view.commitSeries(view.defaults())'), [])

    def test_same_commit_repeated_runs_keep_separate_points(self):
        data = browser_fixture()
        for exp in data['experiments']:
            exp['commit_provenance'] = {'candidate_sha':'1'*40,'candidate_committed_epoch':100}
        actual = self.project(data, 'view.commitSeries({...view.defaults(),skill:"candidate"})')
        self.assertEqual(len(actual), 1)
        self.assertEqual(len(actual[0]['rows']), 2)
        self.assertEqual(len({r['experiment'] for r in actual[0]['rows']}), 2)
