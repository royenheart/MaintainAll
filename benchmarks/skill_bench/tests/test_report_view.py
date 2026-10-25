"""Behavior checks for report navigation, comparison direction and evidence."""
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from skill_bench import report
from test_review import fixture


def browser_fixture():
    judge = {"class": "agent", "id": "independent", "version": 1, "view": "artifact-only", "arm_map_seen": False}
    cohorts, trials, ratings, pairs = [], [], [], []
    for experiment in ("development", "formal"):
        for arm in ("previous", "candidate", "none"):
            identity = {"id": experiment + "-" + arm, "skill": arm, "skill_hash": arm + "-snapshot", "case_id": "case-a", "case_fingerprint": "case-fp", "rubric_fingerprint": "rubric", "suite_fingerprint": "suite", "model": "model", "effort": "low", "backend": "harbor", "backend_fingerprint": "backend", "generation_runtime_fingerprint": "runtime", "invocation_mode": "native", "mechanical_verifier": {"sha256": "verifier"}, "judge": judge}
            cohorts.append(identity)
            for repeat in (1, 2):
                trial_id = experiment + "/" + arm + str(repeat)
                failed = experiment == "formal" and arm == "candidate" and repeat == 2
                trials.append({"id": trial_id, "experiment": experiment, "case_id": "case-a", "arm": arm, "repeat": repeat, "cohort_id": identity["id"], "status": "failed" if failed else "completed", "planned_turns": 3, "recorded_turns": 1 if failed else 3, "privacy": "public", "turns": [{"turn": 1, "status": "failed" if failed else "completed", "seconds": 2, "usage": {"input_tokens": None if failed else 10, "output_tokens": 5}}], "usage": {}})
                ratings.append({"trial_id": trial_id, "experiment": experiment, "case_id": "case-a", "arm": arm, "repeat": repeat, "cohort_id": identity["id"], "turn": 1, "atom": "layout", "dimension": "layout", "score": "unverifiable" if failed else 2, "judge": judge, "review_version": 1, "reason": "Evidence-dependent fixture.", "evidence": []})
        pairs.extend([
            {"experiment": experiment, "case_id": "case-a", "repeat": 1, "left_arm": "previous", "right_arm": "candidate", "left_trial_id": experiment + "/previous1", "right_trial_id": experiment + "/candidate1", "left_cohort_id": experiment + "-previous", "right_cohort_id": experiment + "-candidate", "outcome_for_left": "win", "judge": judge, "reason": "Baseline preferred.", "evidence": []},
            {"experiment": experiment, "case_id": "case-a", "repeat": 2, "left_arm": "candidate", "right_arm": "previous", "left_trial_id": experiment + "/candidate2", "right_trial_id": experiment + "/previous2", "left_cohort_id": experiment + "-candidate", "right_cohort_id": experiment + "-previous", "outcome_for_left": "undetermined", "judge": judge, "reason": "Missing evidence.", "evidence": []},
        ])
    return {"schema_version": 1, "kind": "skill-benchmark-report", "experiment": "history", "current_experiment": "formal", "experiments": [{"id": "development"}, {"id": "formal"}], "cohorts": cohorts, "trials": trials, "ratings": ratings, "pairs": pairs, "media": [{"experiment": "formal", "trial_id": "formal/candidate1", "case_id": "case-a", "case_fingerprint": "case-fp", "turn": 1, "kind": "preview", "name": "selected.png", "sha256": "a" * 64, "export_path": "media/" + "a" * 64 + ".png"}, {"experiment": "formal", "trial_id": "formal/candidate1", "case_id": "case-a", "case_fingerprint": "case-fp", "turn": 1, "kind": "review-evidence", "name": "selected.png", "sha256": "a" * 64, "export_path": "media/" + "a" * 64 + ".png"}, {"experiment": "formal", "trial_id": "formal/candidate1", "turn": 1, "kind": "one-fill-edit", "name": "selected.svg", "sha256": "b" * 64, "export_path": "media/" + "b" * 64 + ".png"}], "case_contexts": [{"case_id": "case-a", "case_fingerprint": "case-fp", "visibility": "public", "title": "Composition study", "turns": [{"turn": 1, "prompt": "Preserve the hierarchy.", "artifacts": []}], "requirements": [{"id": "hierarchy", "turn": 1, "quote": "Preserve the hierarchy."}], "atoms": [{"id": "layout", "dimension": "layout", "criterion": "Hierarchy is preserved.", "active_turns": [1], "requirement_ids": ["hierarchy"], "anchors": {"0": "Lost.", "1": "Partial.", "2": "Preserved."}}]}], "history": []}


class ReportContextTests(unittest.TestCase):
    def test_context_is_frozen_case_allowlist_and_private_content_is_withheld(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            case = manifest["cases"][0]
            case.update(title="Original reference study", turns=[{"prompt": "Keep the original hierarchy.", "attachments": [], "artifacts": [{"path": "drawing.png", "kind": "preview", "format": "png"}], "raw_logs": "do not export"}], requirements=[{"id": "r1", "turn": 1, "quote": "original hierarchy"}], credentials="SECRET")
            case["atoms"][0].update(criterion="Keep hierarchy.", requirement_ids=["r1"], anchors={"0": "Absent", "1": "Partial", "2": "Clear"}, private_key="SECRET")
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            built = report.build_report(manifest, results)
            context = built["case_contexts"][0]
            self.assertEqual(context["title"], case["title"])
            self.assertEqual(context["turns"][0]["prompt"], case["turns"][0]["prompt"])
            self.assertEqual(context["atoms"][0]["anchors"], case["atoms"][0]["anchors"])
            self.assertNotIn("SECRET", json.dumps(context))
            self.assertNotIn("raw_logs", json.dumps(context))
            case["assets"] = [{"id": "private-input", "visibility": "private"}]
            private = report.build_report(manifest, results)["case_contexts"][0]
            self.assertEqual(set(private), {"case_id", "case_fingerprint", "visibility"})

    def test_merge_keeps_context_versions_and_current_media_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            first = report.build_report(manifest, results)
            manifest["id"] = "formal"
            manifest["cases"][0]["version"] = "2"
            second = report.build_report(manifest, results)
            merged = report.merge_reports([first, second])
            self.assertEqual(merged["current_experiment"], "formal")
            self.assertEqual(len(merged["case_contexts"]), 2)
            self.assertTrue(all(item.get("experiment") == "formal" for item in merged["media"]))
            self.assertTrue(all(item["trial_id"].startswith("formal/") for item in merged["media"] if "trial_id" in item))

    def test_merged_media_uses_checked_private_locator_but_exports_only_public_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            first = report.build_report(manifest, results)
            manifest["id"] = "formal"
            merged = report.merge_reports([first, report.build_report(manifest, results)])
            destination = root / "public"
            report.export_report(merged, destination, media_root=root)
            self.assertTrue(report.validate_public_bundle(destination)["valid"])
            public = json.loads((destination / "report.json").read_text())
            self.assertTrue(all(item["trial_id"].startswith("formal/") for item in public["media"]))
            self.assertNotIn("_source_trial_id", json.dumps(public))

    def test_commit_provenance_is_allowlisted_not_inferred_and_budget_changes_cohort(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            self.assertEqual(report.build_report(manifest, results)["experiments"][0]["commit_provenance"], {})
            provenance = {"candidate_sha": "a" * 40, "previous_sha": "b" * 40, "trusted_sha": "c" * 40, "source_run_id": 123, "source_run_attempt": 1, "protocol_id": "skill-baseline-v1", "tracking_key": "d" * 64}
            manifest["commit_provenance"] = {**provenance, "raw_logs": "SECRET"}
            first = report.build_report(manifest, results)
            self.assertEqual(first["experiments"][0]["commit_provenance"], provenance)
            manifest["limits"] = {"max_calls": 3}
            changed = report.build_report(manifest, results)
            self.assertNotEqual(first["trials"][0]["cohort_id"], changed["trials"][0]["cohort_id"])
            manifest["commit_provenance"]["candidate_sha"] = "pretend-commit"
            with self.assertRaisesRegex(ValueError, "commit provenance"):
                report.build_report(manifest, results)


@unittest.skipUnless(shutil.which("node"), "Node is required for pure viewer projection checks")
class ReportViewTests(unittest.TestCase):
    def project(self, data, expression):
        from skill_bench.report_view import LOGIC
        code = "const fs=require('fs');const source=JSON.parse(fs.readFileSync(0,'utf8'));" + LOGIC + "\nconst view=createReportView(source);console.log(JSON.stringify(" + expression + "));"
        result = subprocess.run([shutil.which("node"), "-e", code], input=json.dumps(data), capture_output=True, text=True, check=True, timeout=10)
        return json.loads(result.stdout)

    def test_default_is_current_experiment_and_candidate_direction_is_normalized(self):
        actual = self.project(browser_fixture(), "({state:view.defaults(),summary:view.summarize(view.defaults()),comparison:view.compare(view.defaults())})")
        self.assertEqual(actual["state"]["experiment"], "formal")
        self.assertEqual(actual["state"]["baseline"], "previous")
        self.assertEqual(actual["summary"]["trials"], 6)
        self.assertEqual((actual["summary"]["observed_turns"], actual["summary"]["planned_turns"]), (16, 18))
        self.assertEqual(actual["comparison"]["counts"], {"win": 0, "tie": 0, "loss": 1, "undetermined": 1})
        self.assertEqual(actual["comparison"]["planned_pairs"], 2)

    def test_original_review_order_is_preserved_when_candidate_outcome_flips(self):
        data = browser_fixture()
        actual = self.project(data, "view.compare(view.defaults()).rows.map(row=>({outcome:row.outcome,reason:row.reason,order:view.reviewOrder(row.record,'previous')}))")
        self.assertEqual(actual[0], {"outcome": "loss", "reason": "Baseline preferred.", "order": {"left": "previous", "right": "candidate", "display": ["previous", "candidate"]}})
        self.assertEqual(actual[1]["order"], {"left": "candidate", "right": "previous", "display": ["previous", "candidate"]})
        self.assertEqual(actual[1]["reason"], "Missing evidence.")

    def test_case_navigation_selects_exact_repeat_and_preserves_chosen_turn(self):
        data = browser_fixture()
        actual = self.project(data, "view.caseSelection(view.defaults(),'case-a',2,'case-fp',{repeat:1,turn:2})")
        self.assertEqual(actual["state"]["case_id"], "case-a")
        self.assertEqual(actual["key"], "case-fp")
        self.assertEqual(actual["selection"], {"repeat": 2, "turn": 2})
        self.assertEqual([trial["id"] for trial in actual["trials"]], ["formal/previous2", "formal/candidate2", "formal/none2"])
        self.assertIsNone(self.project(data, "view.caseSelection(view.defaults(),'case-a',3,'case-fp')"))
        self.assertIsNone(self.project(data, "view.caseSelection(view.defaults(),'case-a',2,'wrong-fingerprint')"))

    def test_collapsed_case_summary_counts_recorded_data_and_missing_evidence(self):
        actual = self.project(browser_fixture(), "typeof view.caseOverview==='function'?view.caseOverview(view.defaults(),'case-a','case-fp'):null")
        self.assertIsNotNone(actual, 'Case summaries must be available before evidence is expanded')
        self.assertEqual(actual['trials'], 6)
        self.assertEqual(actual['status_counts'], {'completed':5, 'failed':1})
        self.assertEqual((actual['observed_turns'], actual['planned_turns']), (16, 18))
        self.assertEqual((actual['rated_trials'], actual['rating_rows']), (6, 6))
        self.assertEqual(actual['score_counts']['unverifiable'], 1)
        self.assertEqual(actual['comparison_counts'], {'win':0, 'tie':0, 'loss':1, 'undetermined':1})

    def test_case_summary_does_not_merge_same_id_with_different_fingerprints(self):
        data = browser_fixture()
        next(c for c in data['cohorts'] if c['id']=='formal-candidate')['case_fingerprint']='different-case'
        actual = self.project(data, "typeof view.caseOverview==='function'?[view.caseOverview(view.defaults(),'case-a','case-fp'),view.caseOverview(view.defaults(),'case-a','different-case')]:null")
        self.assertIsNotNone(actual)
        self.assertEqual([row['trials'] for row in actual], [4, 2])

    def test_case_summary_respects_version_filter_and_missing_selection(self):
        data = browser_fixture()
        actual = self.project(data, "typeof view.caseOverview==='function'?{selected:view.caseOverview({...view.defaults(),skill:'previous'},'case-a','case-fp'),missing:view.caseOverview(view.defaults(),'case-a','missing')}:null")
        self.assertIsNotNone(actual)
        self.assertEqual(actual['selected']['trials'], 2)
        self.assertEqual(actual['selected']['rated_trials'], 2)
        self.assertIsNone(actual['missing'])

    def test_chart_data_keeps_counts_unknown_usage_and_conditions_separate(self):
        actual = self.project(browser_fixture(), "typeof view.chartData==='function'?view.chartData(view.defaults()):null")
        self.assertIsNotNone(actual, "Chart projections must derive from selected frozen records")
        self.assertEqual(sum(row["trials"] for row in actual["execution"]), 6)
        candidate = next(row for row in actual["execution"] if row["arm"] == "candidate")
        self.assertEqual(candidate["status_counts"], {"completed": 1, "failed": 1})
        self.assertEqual(len(actual["ratings"]), 3)
        self.assertEqual(sum(row["rating_rows"] for row in actual["ratings"]), 6)
        self.assertEqual(actual["comparisons"][0]["counts"], {"win": 0, "tie": 0, "loss": 1, "undetermined": 1})
        missing = next(row for row in actual["tokens"] if row["field"] == "cached_input_tokens")
        self.assertIsNone(missing["value"])
        self.assertEqual(missing["known"], 0)
        known = next(row for row in actual["tokens"] if row["field"] == "input_tokens")
        self.assertEqual((known["value"], known["known"], known["observed_turns"]), (50, 5, 6))

    def test_chart_filters_do_not_reuse_full_experiment_counts(self):
        actual = self.project(browser_fixture(), "typeof view.chartData==='function'?view.chartData({...view.defaults(),skill:'candidate'}):null")
        self.assertIsNotNone(actual)
        self.assertEqual(len(actual["execution"]), 1)
        self.assertEqual(actual["execution"][0]["trials"], 2)
        self.assertEqual(len(actual["ratings"]), 1)
        self.assertEqual(actual["tokens"][0]["known"], 1)

    def test_evidence_coverage_line_breaks_at_unreviewed_runs(self):
        expression = "typeof view.ratingTrend==='function'?view.ratingTrend([{rating_rows:4,score_counts:{unverifiable:1}},{rating_rows:0,score_counts:{unverifiable:0}},{rating_rows:2,score_counts:{unverifiable:2}},{rating_rows:2,score_counts:{unverifiable:0}}]):null"
        actual = self.project(browser_fixture(), expression)
        self.assertIsNotNone(actual)
        self.assertEqual([point["value"] for point in actual["points"]], [75, None, 0, 100])
        self.assertEqual(actual["connections"], [[2, 3]])
        self.assertEqual(actual["maximum"], 100)

    def test_count_axes_use_integer_ticks_and_contain_recorded_values(self):
        actual = self.project(browser_fixture(), "typeof view.countScale==='function'?[view.countScale(3),view.countScale(69),view.countScale(6515358)]:null")
        self.assertIsNotNone(actual)
        self.assertEqual(actual[0], {"maximum": 3, "ticks": [0, 1, 2, 3]})
        self.assertEqual(actual[1], {"maximum": 80, "ticks": [0, 20, 40, 60, 80]})
        self.assertEqual(actual[2], {"maximum": 8000000, "ticks": [0, 2000000, 4000000, 6000000, 8000000]})

    def test_unknown_and_failure_remain_and_token_subtotals_have_coverage(self):
        actual = self.project(browser_fixture(), "view.summarize({...view.defaults(),skill:'candidate'})")
        self.assertEqual(actual["status_counts"], {"completed": 1, "failed": 1})
        self.assertEqual(actual["score_counts"]["unverifiable"], 1)
        self.assertEqual(actual["usage"]["input_tokens"], {"subtotal": 10, "known": 1, "planned_turns": 6, "observed_turns": 2})

    def test_case_evidence_deduplicates_review_copies_and_does_not_guess_historical_links(self):
        data = browser_fixture()
        data["media"].append({"kind": "review-evidence", "name": "unmapped.png", "sha256": "c" * 64, "export_path": "media/" + "c" * 64 + ".png"})
        actual = self.project(data, "({current:view.mediaFor('formal/candidate1',1),old:view.mediaFor('development/candidate1',1),context:view.contextFor(source.trials.find(t=>t.id==='formal/candidate1'))})")
        self.assertEqual([item["name"] for item in actual["current"]], ["selected.png"])
        self.assertEqual(actual["old"], [])
        self.assertEqual(actual["context"]["title"], "Composition study")

    def test_ab_allows_skill_difference_but_blocks_renderer_or_judge_changes(self):
        data = browser_fixture()
        self.assertTrue(self.project(data, "view.compare(view.defaults()).rows[0].comparable"))
        next(c for c in data["cohorts"] if c["id"] == "formal-candidate")["generation_runtime_fingerprint"] = "different-renderer"
        row = self.project(data, "view.compare(view.defaults()).rows[0]")
        self.assertFalse(row["comparable"])
        self.assertIn("generation_runtime_fingerprint", row["condition_differences"])
        self.assertEqual(self.project(data, "view.compare(view.defaults()).counts['undetermined']"), 2)

    def test_rating_filters_join_trials_without_merging_process_and_artifact_views(self):
        data = browser_fixture()
        data["ratings"][0]["judge"] = {**data["ratings"][0]["judge"], "view": "notes-process"}
        actual = self.project(data, "({formal:view.summarize({...view.defaults(),judge:'agent:independent',review_version:'1'}),development:view.summarize({...view.defaults(),experiment:'development',review_view:''})})")
        self.assertEqual(actual["formal"]["trials"], 6)
        self.assertEqual(actual["formal"]["independent_review"]["views"], ["artifact-only"])
        self.assertEqual(set(actual["development"]["independent_review"]["views"]), {"artifact-only", "notes-process"})

    def test_document_uses_collapsed_technical_details_and_no_eager_evidence_wall(self):
        rendered = report.render_html(browser_fixture())
        self.assertIn('id="experiment-select"', rendered)
        self.assertIn('id="baseline-commit-select"', rendered)
        self.assertIn('id="case-select"', rendered)
        self.assertIn('id="advanced-filters"', rendered)
        self.assertIn('id="technical-details"', rendered)
        self.assertNotIn('id="technical-details" open', rendered)
        self.assertNotIn('<figure>', rendered)
        self.assertNotIn('https://fonts.', rendered)
        self.assertIn('lang="en"', rendered)

    def test_document_has_numbered_chapters_and_matching_contents(self):
        rendered = report.render_html(browser_fixture())
        chapters = [
            ('evaluation-setup', '1. Evaluation setup'),
            ('overview', '2. Execution and review coverage'),
            ('version-comparison', '3. Candidate versus baseline'),
            ('case-evidence', '4. Inspect the case evidence'),
            ('commit-history', '5. Evaluation history'),
        ]
        self.assertEqual(re.findall(r'<h2>(.*?)</h2>', rendered), [title for _, title in chapters])
        contents = re.search(r'<nav class="navigation".*?</nav>', rendered).group()
        self.assertIn('<ol>', contents)
        for anchor, title in chapters:
            self.assertIn(f'<a href="#{anchor}">{title}</a>', contents)
            self.assertIn(f'<section id="{anchor}"><h2>{title}</h2>', rendered)
        setup = rendered.split('<section id="evaluation-setup">', 1)[1].split('</section>', 1)[0]
        comparison = rendered.split('<section id="version-comparison">', 1)[1].split('</section>', 1)[0]
        self.assertIn('id="candidate-commit-select"', setup)
        self.assertIn('id="skill-diff"', setup)
        self.assertIn('id="comparison-summary"', comparison)
        header = rendered.split('<header>', 1)[1].split('</header>', 1)[0]
        self.assertNotIn('id="comparison-summary"', header)
        self.assertNotIn('id="method-details"', rendered)
        self.assertLess(rendered.index('id="glossary"'), rendered.index('<section id="evaluation-setup">'))
        self.assertIn('id="term-tooltip"', rendered)

    def test_single_evaluation_has_no_empty_history_chapter(self):
        data = browser_fixture()
        data['experiments'] = [e for e in data['experiments'] if e['id'] == 'formal']
        for key in ('trials', 'ratings', 'pairs'):
            data[key] = [r for r in data[key] if r['experiment'] == 'formal']
        actual = self.project(data, 'view.historyState(view.defaults())')
        self.assertFalse(actual['visible'])
        self.assertFalse(actual['commit_chart'])
        rendered = report.render_html(data)
        self.assertIn('<section id="commit-history" hidden>', rendered)

    def test_multiple_snapshot_evaluations_have_history_without_empty_commit_chart(self):
        actual = self.project(browser_fixture(), 'view.historyState(view.defaults())')
        self.assertTrue(actual['visible'])
        self.assertFalse(actual['commit_chart'])

    def test_commit_history_needs_multiple_matching_recorded_evaluations(self):
        data = browser_fixture()
        for index, metadata in enumerate(data['experiments'], 1):
            metadata['commit_provenance'] = {'candidate_sha': str(index) * 40,
                'previous_sha': '0' * 40, 'protocol_id': 'same-protocol'}
        self.assertTrue(self.project(data, 'view.historyState(view.defaults())')['commit_chart'])
        for cohort in data['cohorts']:
            if cohort['id'].startswith('formal-'):
                cohort['generation_runtime_fingerprint'] = 'changed-environment'
        actual = self.project(data, 'view.historyState(view.defaults())')
        self.assertTrue(actual['visible'])
        self.assertFalse(actual['commit_chart'])
