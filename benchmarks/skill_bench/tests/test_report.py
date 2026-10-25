"""Checks for cohort separation, unknown ratings and safe report publication."""
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from skill_bench import report, review
from test_review import fixture

class ReportTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for renderer logic checks")
    def test_history_plot_connects_only_exact_cohorts_and_preserves_observation_denominators(self):
        judge = {"class": "agent", "id": "rater", "version": 1}
        data = {"experiment": "history", "cohorts": [{"id": arm, "skill": arm, "case_id": "case", "suite_fingerprint": "suite", "case_fingerprint": "case", "judge": judge} for arm in ("candidate", "previous")], "trials": [], "ratings": [], "pairs": [], "history": []}
        for index, experiment in enumerate(("first <experiment>", "second")):
            for arm in ("candidate", "previous"):
                trial_id = experiment + "/" + arm
                scores = ([2, "unverifiable"] if index == 0 else [1, 2, "unverifiable"]) if arm == "candidate" else ([0, "unverifiable", "unverifiable"] if index == 0 else [2])
                data["trials"].append({"id": trial_id, "experiment": experiment, "case_id": "case", "arm": arm, "repeat": 1, "cohort_id": arm, "status": "completed", "quality_status": "exploratory_independent_review", "seconds": None, "usage": {}, "planned_turns": 1, "recorded_turns": 1, "result_record": "present", "turns": [{"turn": 1, "delivery_pass": None, "preservation_pass": None}]})
                for number, score in enumerate(scores):
                    data["ratings"].append({"trial_id": trial_id, "experiment": experiment, "case_id": "case", "arm": arm, "repeat": 1, "cohort_id": arm, "judge": judge, "review_version": 1, "turn": 1, "dimension": "layout", "atom": "atom-" + str(number), "score": score, "reason": "Synthetic UI fixture only.", "evidence": []})
                data["history"].append({"experiment": experiment, "cohort_id": arm, "trials": 1, "case_repeat_units": 1, "atom_observations": len(scores), "score_counts": {str(score): scores.count(score) for score in (0, 1, 2, "unverifiable")}, "seconds": None})
        data["cohorts"].append({**data["cohorts"][0], "id": "candidate-execution", "judge": {"class": "unassessed", "id": "none", "version": 0}})
        data["trials"].append({**data["trials"][2], "id": "second/failed-before-future-ratings", "repeat": 2, "cohort_id": "candidate-execution", "status": "failed", "quality_status": "unassessed", "planned_turns": 3, "recorded_turns": 1})
        from skill_bench.report_view import LOGIC
        checks = r"""const view=createReportView(data),state={...view.defaults(),experiment:''};const all=view.historySeries(state);const arm=view.historySeries({...state,skill:'candidate'});const filtered=view.historySeries({...state,repeat:'1',judge:'agent:rater',review_version:'1'});data.history=data.history.filter(r=>r.experiment==='first <experiment>');const single=view.historySeries(state);data.history=[];console.log(JSON.stringify({all,arm,filtered,single,empty:view.historySeries(state)}));"""
        result = subprocess.run([shutil.which("node"), "-e", "const fs=require('fs');const data=JSON.parse(fs.readFileSync(0,'utf8'));" + LOGIC + checks], input=json.dumps(data), text=True, capture_output=True, timeout=10, check=True)
        observed = json.loads(result.stdout)
        self.assertEqual({row["cohort_id"] for row in observed["all"]}, {"candidate", "previous"})
        self.assertTrue(all(row["connections"] == [[0, 1]] for row in observed["all"]))
        self.assertEqual(observed["arm"][0]["cohort_id"], "candidate")
        candidate = next(row for row in observed["all"] if row["cohort_id"] == "candidate")
        self.assertEqual(candidate["rows"][0]["score_counts"]["unverifiable"], 1)
        second = candidate["rows"][1]
        self.assertEqual((second["cases"], second["repeats"], second["trials"], second["observed_turns"], second["planned_turns"], second["rating_rows"]), (1, 2, 2, 2, 4, 3))
        self.assertEqual(second["status_counts"], {"completed": 1, "failed": 1})
        self.assertEqual(sum(len(row["rows"]) for row in observed["filtered"]), 4)
        self.assertTrue(all(row["connections"] == [] for row in observed["single"]))
        self.assertEqual(observed["empty"], [])
        rendered = report.render_html(data)
        self.assertIn('id="history-trends"', rendered)
        self.assertIn('id="history-metric"', rendered)
        self.assertIn("existing rating rows", rendered)
        self.assertIn("not all planned requirements or future turns", rendered)
        self.assertNotIn("first <experiment>", rendered)

    @unittest.skipUnless(shutil.which("node"), "Node is needed for renderer logic checks")
    def test_judge_filters_join_trials_and_history_repeats_keep_experiment_units(self):
        judge = {"class": "agent", "id": "rater", "version": 1}
        data = {"experiment": "history", "cohorts": [{"id": "mechanical", "suite_fingerprint": "suite", "case_fingerprint": "case", "judge": {"class": "unassessed"}}, {"id": "rated", "suite_fingerprint": "suite", "case_fingerprint": "case", "judge": judge}], "trials": [], "ratings": [], "pairs": [], "history": []}
        for experiment in ("first", "second"):
            for arm in ("previous", "candidate"):
                trial_id = experiment + "/" + arm
                data["trials"].append({"id": trial_id, "experiment": experiment, "case_id": "case", "arm": arm, "repeat": 1, "cohort_id": "mechanical", "status": "completed", "quality_status": "exploratory_independent_review", "seconds": None, "usage": {field: None for field in report.TOKEN_FIELDS}, "turns": [{"turn": 1, "delivery_pass": None, "preservation_pass": None, "source_proofs": []}]})
                data["ratings"].append({"trial_id": trial_id, "experiment": experiment, "case_id": "case", "arm": arm, "repeat": 1, "cohort_id": "rated", "judge": judge, "review_version": 1, "turn": 1, "dimension": "layout", "atom": "grouping", "score": "unverifiable", "reason": "UI fixture.", "evidence": []})
        from skill_bench.report_view import LOGIC
        checks = "const view=createReportView(data),state={...view.defaults(),experiment:''};console.log(JSON.stringify({current:view.summarize(view.defaults()),all:view.summarize(state),judged:view.summarize({...state,judge:'agent:rater',review_version:'1'})}));"
        result = subprocess.run([shutil.which("node"), "-e", "const fs=require('fs');const data=JSON.parse(fs.readFileSync(0,'utf8'));" + LOGIC + checks], input=json.dumps(data), text=True, capture_output=True, timeout=10, check=True)
        counts = json.loads(result.stdout)
        self.assertEqual((counts["current"]["cases"], counts["current"]["trials"], counts["current"]["rating_rows"]), (1, 2, 2))
        for key in ("all", "judged"):
            self.assertEqual((counts[key]["cases"], counts[key]["case_repeat_units"], counts[key]["trials"], counts[key]["rating_rows"]), (1, 2, 4, 4))

    def test_report_keeps_samples_and_mechanical_checks_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            result = report.build_report(manifest, results)
            self.assertEqual(len(result.get("trials", [])), 2)
            self.assertEqual(result["sample_sizes"]["independent_cases"], 1)
            self.assertIsNone(result["automatic_quality_pass"])
            self.assertEqual(result["ratings"], [])
            self.assertNotIn("private-session", json.dumps(result))

    def test_closed_run_missing_results_preserve_planned_coverage_without_unsupported_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            manifest["cases"][0]["turns"] = [{"prompt": "Inspect turn " + str(number), "artifacts": []} for number in (1, 2, 3)]
            results = [json.loads((root / "trials/trial-previous/result.json").read_text())]
            for attempted in (False, True):
                events = [{"type": "run_started"}]
                if attempted:
                    events.append({"type": "turn_started", "trial_id": "trial-candidate", "turn": 1})
                events.append({"type": "run_finished", "reason": "PRIVATE RAW REASON MUST NOT EXPORT"})
                data = report.build_report(manifest, results, execution_events=events)
                absent = next(trial for trial in data["trials"] if trial["id"] == "trial-candidate")
                self.assertEqual(absent["status"], "interrupted" if attempted else "not_attempted")
                self.assertEqual(absent["quality_status"], "unassessed")
                self.assertEqual(data["sample_sizes"]["trials"], 2)
                self.assertEqual(data["sample_sizes"]["planned_turns"], 6)
                self.assertEqual(data["sample_sizes"]["turn_observations"], 1)
                self.assertEqual(data["coverage"]["missing_trial_results"], 1)
                self.assertIsNone(absent["usage"]["input_tokens"])
                self.assertNotIn("PRIVATE RAW REASON", json.dumps(data))
                self.assertEqual(data["ratings"], [])
                second = json.loads(json.dumps(data))
                second["experiment"] = "second-experiment"
                second["report_fingerprint"] = report.canonical_hash(second)
                history = report.merge_reports([data, second])
                self.assertEqual(history["sample_sizes"]["planned_turns"], 12)
                self.assertEqual(history["sample_sizes"]["turn_observations"], 2)
                self.assertEqual(history["coverage"]["missing_trial_results"], 2)
            for events in (None, [], [{"type": "run_started"}], [{"type": "run_started"}, {"type": "run_finished"}, {"type": "call_reserved", "trial_id": "trial-candidate"}]):
                with self.subTest(events=events), self.assertRaisesRegex(ValueError, "closed"):
                    report.build_report(manifest, results, execution_events=events)
            invalid = json.loads(json.dumps(results))
            invalid[0]["status"] = "not_attempted"
            with self.assertRaisesRegex(ValueError, "status"):
                report.build_report(manifest, invalid, execution_events=[{"type": "run_started"}, {"type": "run_finished"}])

    def test_sealed_invalid_solver_previews_are_withheld_but_integrity_changes_reject_export(self):
        from test_runner import RunnerTests
        from skill_bench.experiment import load_experiment
        from skill_bench.runner import run_experiment
        from skill_bench.store import load_results, read_events
        fixture_case = RunnerTests()
        fixture_case.setUp()
        try:
            root = fixture_case.root / "run"
            state = run_experiment(root, execute=True, adapter=fixture_case.adapter)
            self.assertEqual(state["state"], "completed_with_failures")
            packet_path = fixture_case.root / "review"
            packet = review.export_review(root, packet_path, seed=13)
            for turn in packet["entries"][0]["turns"]:
                self.assertEqual(turn["artifacts"], [])
                self.assertEqual(len(turn["withheld_previews"]), 1)
                self.assertTrue(turn["withheld_previews"][0]["withheld_reason"])
                status = json.loads((packet_path / turn["status_evidence"]["path"]).read_text())
                self.assertFalse(status["delivery_pass"])
            data = report.build_report(load_experiment(root), load_results(root), execution_events=read_events(root))
            destination = fixture_case.root / "public"
            report.export_report(data, destination, media_root=root)
            public = json.loads((destination / "report.json").read_text())
            self.assertEqual(public["media"], [])
            self.assertEqual(len(public["withheld_previews"]), 2)
            self.assertEqual(public["coverage"]["withheld_preview_count"], 2)
            self.assertIn("Withheld previews", (destination / "index.html").read_text())
            self.assertFalse(public["trials"][0]["turns"][0]["delivery_pass"])
            self.assertTrue(report.validate_public_bundle(destination)["valid"])
            source = root / "trials" / data["media"][0]["trial_id"] / data["media"][0]["path"]
            source.write_bytes(b"changed invalid artifact")
            with self.assertRaisesRegex(ValueError, "hash|size"):
                report.export_report(data, fixture_case.root / "tampered-public", media_root=root)
            with self.assertRaisesRegex(ValueError, "hash|size"):
                review.export_review(root, fixture_case.root / "tampered-review", seed=14)
        finally:
            fixture_case.doCleanups()

    def test_independent_unknown_review_is_not_zero_and_changes_cohort(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest = fixture(root)
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            dest = Path(directory) / "packet"
            with mock.patch("skill_bench.experiment.load_experiment", side_effect=lambda root: json.loads((Path(root) / "manifest.json").read_text())):
                packet = review.export_review(root, dest, seed=5)
            document = json.loads((dest / "ratings-template.json").read_text())
            document["reviewer"].update(id="independent-agent", **{"class": "agent"})
            for row in document["ratings"]:
                entry = next(e for e in packet["entries"] if e["id"] == row["entry"])
                artifact = entry["turns"][0]["artifacts"][0]
                row.update(evidence=[{"path": artifact["path"], "sha256": artifact["sha256"]}], reason="Physical deformation cannot be confirmed from the static artifact.")
            artifact = packet["entries"][0]["turns"][0]["artifacts"][0]
            document["pairs"][0].update(evidence=[{"path": artifact["path"], "sha256": artifact["sha256"]}], reason="Static evidence does not support a preference.")
            mapping = json.loads(next((root / "reviews").glob("*.arm-map.json")).read_text())
            bundle = {"packet": packet, "document": document, "arm_map": mapping}
            result = report.build_report(manifest, results, [bundle])
            self.assertEqual(result["sample_sizes"]["independent_cases"], 1)
            self.assertEqual(result["sample_sizes"]["atom_observations"], 2)
            self.assertEqual(result["pairs"][0]["rubric_fingerprint"], next(cohort for cohort in result["cohorts"] if cohort["judge"]["class"] == "agent")["rubric_fingerprint"])
            self.assertEqual(result["dimensions"][0]["score_counts"]["0"], 0)
            self.assertEqual(result["dimensions"][0]["score_counts"]["unverifiable"], 1)
            self.assertIsNone(result["automatic_quality_pass"])
            self.assertTrue(all(trial["quality_status"] == "exploratory_independent_review" for trial in result["trials"]))
            historical = report.merge_reports([result])
            for cohort_id in {rating["cohort_id"] for rating in result["ratings"]}:
                point = next(row for row in historical["history"] if row["cohort_id"] == cohort_id)
                self.assertEqual((point["trials"], point.get("independent_cases"), point.get("turn_observations")), (1, 1, 1))
                self.assertEqual(point["score_counts"]["unverifiable"], 1)
            with_failure = json.loads(json.dumps(result))
            original_trial = with_failure["trials"][0]
            original_trial["planned_turns"] = 1
            with_failure["trials"].append({**original_trial, "id": "unrated-failed-repeat", "repeat": 2, "status": "failed", "quality_status": "unassessed", "planned_turns": 3, "recorded_turns": 1})
            with_failure["report_fingerprint"] = report.canonical_hash(with_failure)
            history_with_failure = report.merge_reports([with_failure])
            rated_cohort = next(rating["cohort_id"] for rating in with_failure["ratings"] if rating["trial_id"] == original_trial["id"])
            point = next(row for row in history_with_failure["history"] if row["cohort_id"] == rated_cohort)
            self.assertEqual((point["trials"], point["turn_observations"], point["planned_turns"]), (2, 2, 4))
            self.assertEqual(point["trial_status_counts"], {"completed": 1, "failed": 1})
            self.assertEqual((point["atom_observations"], point["score_counts"]["unverifiable"]), (1, 1))
            self.assertNotIn(mapping["private_key"], json.dumps(result))
            changed_packet = json.loads(json.dumps(packet))
            changed_packet["entries"][0]["prompts"] = ["Altered rubric input."]
            with self.assertRaisesRegex(ValueError, "packet fingerprint"):
                report.build_report(manifest, results, [{**bundle, "packet": changed_packet}])
            corrupted = json.loads(json.dumps(mapping))
            corrupted["private_key"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "blind key|fingerprint"):
                report.build_report(manifest, results, [{**bundle, "arm_map": corrupted}])
            corrupted.pop("private_key")
            with self.assertRaisesRegex(ValueError, "private blind key"):
                report.build_report(manifest, results, [{**bundle, "arm_map": corrupted}])
            changed = json.loads(json.dumps(manifest))
            changed["cases"][0]["version"] = "2"
            newer = report.build_report(changed, results)
            self.assertNotEqual(result["trials"][0]["cohort_id"], newer["trials"][0]["cohort_id"])

    def test_html_escapes_input_and_exports_only_hash_allowlisted_raster(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest = fixture(root)
            manifest["id"] = '</script><img src=x onerror="alert(1)">'
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            data = report.build_report(manifest, results)
            dest = Path(directory) / "public"
            summary = report.export_report(data, dest, media_root=root)
            self.assertTrue(summary["sanitized"])
            self.assertTrue(report.validate_public_bundle(dest)["valid"])
            with mock.patch.object(report, "_SCRIPT", report._SCRIPT + "\n// A different trusted renderer revision.\n"):
                with self.assertRaisesRegex(ValueError, "trusted escaped renderer"):
                    report.validate_public_bundle(dest)
            self.assertTrue(report.validate_public_bundle(dest)["valid"])
            (dest / "extra-raw.log").write_text("private trace")
            with self.assertRaisesRegex(ValueError, "allowlist"):
                report.validate_public_bundle(dest)
            (dest / "extra-raw.log").unlink()
            rendered = (dest / "index.html").read_text()
            self.assertNotIn(manifest["id"], rendered)
            self.assertIn("Content-Security-Policy", rendered)
            self.assertNotIn("https://cdn", rendered)
            self.assertEqual(len(list((dest / "media").iterdir())), 2)
            public = json.loads((dest / "report.json").read_text())
            self.assertNotIn("private-session", json.dumps(public))
            self.assertNotIn("turn1/artifacts", json.dumps(public))
            self.assertIsNone(public["aggregate_aesthetic_score"])

    def test_public_export_rejects_secret_symlink_and_byte_limit(self):
        for bad in ("secret", "symlink", "oversize"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "run"
                root.mkdir()
                manifest = fixture(root)
                results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
                data = report.build_report(manifest, results)
                if bad == "secret":
                    data["limitations"].append("API_KEY=secret")
                elif bad == "symlink":
                    item = data["media"][0]
                    path = root / "trials" / item["trial_id"] / item["path"]
                    outside = Path(directory) / "outside.png"
                    outside.write_bytes(path.read_bytes())
                    path.unlink()
                    path.symlink_to(outside)
                with self.assertRaises(ValueError):
                    report.export_report(data, Path(directory) / "public", media_root=root, max_file_bytes=2 if bad == "oversize" else 8388608)
                self.assertFalse((Path(directory) / "public").exists())

    def test_missing_usage_is_unknown_and_self_rating_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            results[0]["turns"][0]["usage"] = {}
            results[0]["self_ratings"] = [{"score": 2, "atom": "relation"}]
            data = report.build_report(manifest, results)
            trial = next(row for row in data["trials"] if row["id"] == results[0]["trial_id"])
            self.assertIsNone(trial["usage"]["input_tokens"])
            self.assertEqual(data["ratings"], [])

    def test_history_deduplicates_reports_and_never_merges_changed_cohorts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            manifest["mechanical_verifier"] = {"sha256":"same-verifier", "source_verifier_sha256":"same-source-verifier", "reopen_sources":False}
            manifest["limits"] = {"max_calls": 6, "wall_seconds": 60}
            manifest["order_seed"] = 20261009
            first = report.build_report(manifest, results)
            newer_manifest = json.loads(json.dumps(manifest))
            newer_manifest["id"] = "experiment-2"
            newer_manifest["arms"][1]["skill_hash"] = "new-skill-hash"
            second = report.build_report(newer_manifest, results)
            merged = report.merge_reports([first, first, second])
            self.assertEqual(len(merged["trials"]), 4)
            self.assertEqual(merged["sample_sizes"]["independent_cases"], 1)
            self.assertEqual(len(merged["cohorts"]), 3)
            self.assertEqual(len(merged["history"]), 4)
            self.assertEqual(merged["historical_media_omitted"], 2)

    def test_private_reference_derivatives_and_reasons_never_become_public_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            manifest["cases"][0]["assets"] = [{"id":"private-input", "visibility":"private", "path":"secret.png", "sha256":"0"*64}]
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            data = report.build_report(manifest, results)
            self.assertTrue(all(row["privacy"] == "private" for row in data["trials"]))
            self.assertEqual(data["media"], [])
            dest = root / "public"
            report.export_report(data, dest, media_root=root)
            self.assertFalse((dest / "media").exists())
            self.assertNotIn("secret.png", (dest / "report.json").read_text())

    def test_mechanical_verifier_identity_changes_cohort_but_regrade_id_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            manifest["mechanical_verifier"] = {"sha256":"grader-a", "source_verifier_sha256":"source-a", "reopen_sources":True, "regrade_id":"one"}
            first = report.build_report(manifest, results)
            manifest["mechanical_verifier"]["regrade_id"] = "two"
            same = report.build_report(manifest, results)
            self.assertEqual(first["trials"][0]["cohort_id"], same["trials"][0]["cohort_id"])
            manifest["mechanical_verifier"]["sha256"] = "grader-b"
            changed = report.build_report(manifest, results)
            self.assertNotEqual(first["trials"][0]["cohort_id"], changed["trials"][0]["cohort_id"])

    def test_source_runtime_changes_form_separate_verifier_cohorts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            manifest["mechanical_verifier"] = {"sha256": "grader", "source_verifier_sha256": "source", "source_runtime_fingerprint": "runtime-a", "reopen_sources": True, "regrade_id": "one"}
            first = report.build_report(manifest, results)
            manifest["id"] = "second-experiment"
            manifest["mechanical_verifier"]["source_runtime_fingerprint"] = "runtime-b"
            second = report.build_report(manifest, results)
            self.assertNotEqual(first["trials"][0]["cohort_id"], second["trials"][0]["cohort_id"])
            self.assertEqual(second["mechanical_verifier"]["source_runtime_fingerprint"], "runtime-b")
            self.assertEqual(len(report.merge_reports([first, second])["cohorts"]), 4)

    def test_generation_renderer_and_invocation_mode_each_prevent_cohort_merging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            manifest["mechanical_verifier"] = {"sha256": "grader", "source_verifier_sha256": None, "source_runtime_fingerprint": None, "reopen_sources": False}
            manifest["runtime"] = {"renderer": "/home/private/renderer-a", "platform": "linux", "adapter_sha256": "same-adapter"}
            manifest["mode"] = "explicit_skill_provision"
            first = report.build_report(manifest, results)
            self.assertNotIn("/home/private", json.dumps(first))
            for field, value in (("renderer", "/home/private/renderer-b"), ("mode", "automatic_discovery")):
                with self.subTest(field=field):
                    changed = json.loads(json.dumps(manifest))
                    changed["id"] = "second-experiment"
                    if field == "renderer":
                        changed["runtime"]["renderer"] = value
                    else:
                        changed["mode"] = value
                    second = report.build_report(changed, results)
                    self.assertNotEqual(first["trials"][0]["cohort_id"], second["trials"][0]["cohort_id"])
                    self.assertEqual(len(report.merge_reports([first, second])["cohorts"]), 4)
                    self.assertNotIn("/home/private", json.dumps(second))
            self.assertEqual(first["cohorts"][0]["generation_runtime_fingerprint"], report.canonical_hash(manifest["runtime"]))
            self.assertEqual(first["cohorts"][0]["invocation_mode"], "explicit_skill_provision")

    def test_command_usage_is_aggregated_only_when_every_turn_is_observed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            result = results[0]
            result["turns"][0]["usage"].update(tool_commands=7, nonzero_tool_commands=2, cli_warning_items=1, cli_error_items=0, credentials="PRIVATE NOT EXPORTABLE")
            second = json.loads(json.dumps(result["turns"][0]))
            second["turn"] = 2
            second["usage"].update(tool_commands=3, nonzero_tool_commands=0, cli_warning_items=0, cli_error_items=1)
            result["turns"].append(second)
            data = report.build_report(manifest, results)
            trial = next(row for row in data["trials"] if row["id"] == result["trial_id"])
            self.assertEqual([trial["usage"][key] for key in ("tool_commands", "nonzero_tool_commands", "cli_warning_items", "cli_error_items")], [10, 2, 1, 1])
            self.assertEqual(trial["turns"][0]["usage"]["tool_commands"], 7)
            self.assertNotIn("PRIVATE NOT EXPORTABLE", json.dumps(data))
            other = next(row for row in data["trials"] if row["id"] != result["trial_id"])
            self.assertIsNone(other["usage"]["tool_commands"])
            for invalid in (None, True, 1.5, -1):
                with self.subTest(invalid=invalid):
                    second["usage"]["tool_commands"] = invalid
                    changed = report.build_report(manifest, results)
                    self.assertIsNone(next(row for row in changed["trials"] if row["id"] == result["trial_id"])["usage"]["tool_commands"])

    def test_public_media_keeps_only_declared_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            manifest["cases"][0]["turns"] = [{"artifacts":[{"path":"drawing.png"}]}]
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            data = report.build_report(manifest, results)
            self.assertEqual({item["name"] for item in data["media"]}, {"drawing.png"})
            manifest["cases"][0]["turns"][0]["artifacts"] = []
            data = report.build_report(manifest, results)
            self.assertEqual({item["name"] for item in data["media"]}, {"additional-preview"})

    def test_source_proof_keeps_narrow_scope_and_hash_checked_rebuild_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixture(root)
            manifest["cases"][0]["turns"] = [{"artifacts":[{"path":"drawing.png"},{"path":"editable.svg"}]}]
            results = [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]
            source_sha = "a" * 64
            results[0]["turns"][0]["artifacts"].append({"path":"editable.svg", "kind":"editable", "format":"svg", "sha256":source_sha, "size":0, "snapshot":"source.svg"})
            image = results[0]["turns"][0]["artifacts"][0]
            rebuilt = root / "verifier/rebuilt.png"
            rebuilt.parent.mkdir()
            rebuilt.write_bytes((root / "trials" / results[0]["trial_id"] / image["snapshot"]).read_bytes())
            results[0]["turns"][0]["source_verification"] = [{"source_sha256":source_sha, "source_reopen_verified":True, "source_editability_verified":True, "rendered":{"source":{"path":"verifier/rebuilt.png", "sha256":image["sha256"], "size":image["size"]}}}]
            data = report.build_report(manifest, results)
            proof = next(trial for trial in data["trials"] if trial["id"] == results[0]["trial_id"])["turns"][0]["source_proofs"][0]
            self.assertTrue(proof["one_fill_edit_verified"])
            self.assertIn("one existing SVG fill", proof["scope"])
            dest = root / "public"
            report.export_report(data, dest, media_root=root)
            self.assertIn("source-rebuild", (dest / "index.html").read_text())
            self.assertIn("whole-project readiness claim", (dest / "index.html").read_text())
            self.assertTrue(report.validate_public_bundle(dest)["valid"])

if __name__ == "__main__":
    unittest.main()
