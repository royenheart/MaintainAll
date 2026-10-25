"""Local-private evidence stays inspectable without becoming publishable."""
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from skill_bench import report
from test_review import fixture, pixel_png, seal_result


def private_fixture(root):
    manifest = fixture(root)
    case = manifest["cases"][0]
    reference = root / "reference.png"
    reference.write_bytes(pixel_png(130))
    case.update(visibility="private", title="Original private composition", assets=[{"id": "reference", "path": "reference.png", "sha256": hashlib.sha256(reference.read_bytes()).hexdigest(), "size": reference.stat().st_size, "visibility": "private"}], turns=[{"prompt": "Preserve the curved title contour.", "attachments": ["reference"], "artifacts": [{"path": "drawing.png", "kind": "preview", "format": "png"}]}])
    (root / "manifest.json").write_text(json.dumps(manifest))
    return manifest, [json.loads(path.read_text()) for path in root.glob("trials/*/result.json")]


class PrivateReportTests(unittest.TestCase):
    def test_opt_in_failed_turn_withholds_persisted_images_but_retains_hashes_and_status(self):
        from skill_bench import private_report
        for output_event, expected in [('', 'failed-no-model-output'), ('{"type":"item.completed","item":{"type":"agent_message","text":"Partial adjustment"}}\n', 'partial-model-output')]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'run'
                root.mkdir()
                manifest, results = private_fixture(root)
                for result in results:
                    result.update(status='failed', backend={'id': 'local_codex'})
                    result['turns'][0]['status'] = 'failed'
                    log = root / 'trials' / result['trial_id'] / 'turn-1/events.jsonl'
                    log.parent.mkdir()
                    log.write_text('{"type":"turn.started"}\n' + output_event + '{"type":"turn.failed","error":{"message":"Discovery connection failed"}}\n')
                original = json.dumps(results, sort_keys=True)
                legacy = private_report.build_local_report(manifest, results)
                local = private_report.build_local_report(manifest, results, skill_root=root, evidence_scope='failed-turn-v1')
                self.assertEqual(json.dumps(results, sort_keys=True), original)
                self.assertNotIn('evidence_scope', legacy)
                self.assertEqual(local['evidence_scope'], 'failed-turn-v1')
                self.assertTrue(all(trial['turns'][0]['evidence_status'] == expected for trial in local['trials']))
                derived = [item for item in local['media'] if item.get('trial_id')]
                self.assertEqual(len(derived), 0 if not output_event else 2)
                if not output_event:
                    record = local['trials'][0]['turns'][0]
                    self.assertIsNone(record['delivery_pass'])
                    self.assertTrue(record['persisted_delivery_pass'])
                    self.assertEqual(len(record['persisted_artifact_inventory']), 1)
                    self.assertNotIn('snapshot', json.dumps(record['persisted_artifact_inventory']))
                rendered = private_report.render_local_html(local)
                self.assertIn('Failed-turn evidence scope', rendered)
                self.assertIn('partial snapshot', rendered)

    def test_new_failed_turn_condition_enters_judge_and_cohort_identity(self):
        from skill_bench import private_report, review
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            manifest, results = private_fixture(root)
            packet_root = Path(directory) / 'packet'
            with mock.patch('skill_bench.experiment.load_experiment', return_value=manifest):
                packet = review.export_review(root, packet_root, seed=517, allow_private=True, evidence_scope='failed-turn-v1')
            document = json.loads((packet_root / 'ratings-template.json').read_text())
            document['reviewer'].update(id='scope-fixture', **{'class': 'human'})
            evidence = packet['entries'][0]['turns'][0]['status_evidence']
            for row in document['ratings'] + document['pairs']:
                row.update(reason='The scoped condition remains explicit.', evidence=[{'path': evidence['path'], 'sha256': evidence['sha256']}])
            mapping = json.loads(next((root / 'reviews').glob('*.arm-map.json')).read_text())
            bundle = {'packet': packet, 'document': document, 'arm_map': mapping}
            local = private_report.build_local_report(manifest, results, [bundle])
            self.assertEqual(local['evidence_scope'], 'failed-turn-v1')
            self.assertTrue(all(row['judge']['failed_turn_evidence_scope'] == 'failed-turn-v1' for row in local['ratings']))
            rated_cohorts = {row['cohort_id'] for row in local['ratings']}
            self.assertTrue(all(cohort['judge'].get('failed_turn_evidence_scope') == 'failed-turn-v1' for cohort in local['cohorts'] if cohort['id'] in rated_cohorts))

    def notes_fixture(self, root, packet_root, *, view="notes-process", text="# Analysis\n术语解释：对齐让文字共享同一条边。\n<script>globalThis.fakeQuality=100</script>\n"):
        from skill_bench import review
        manifest, results = private_fixture(root)
        manifest["cases"][0]["turns"][0]["artifacts"].append({"path": "analysis.md", "kind": "notes", "format": "md"})
        for result in results:
            path = root / "trials" / result["trial_id"] / "turn1/artifacts/analysis.md"
            path.write_text(text, encoding="utf-8")
            result["turns"][0]["artifacts"].append({"path": "analysis.md", "snapshot": "turn1/artifacts/analysis.md", "kind": "notes", "format": "md", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size})
            result_path = root / "trials" / result["trial_id"] / "result.json"
            result_path.write_text(json.dumps(result))
            seal_result(result_path)
        with mock.patch("skill_bench.experiment.load_experiment", return_value=manifest):
            packet = review.export_review(root, packet_root, seed=43, allow_private=True, view=view)
        document = json.loads((packet_root / "ratings-template.json").read_text())
        document["reviewer"].update(id="text-review-fixture", **{"class": "human"})
        evidence = packet["entries"][0]["turns"][0]["status_evidence"]
        for row in document["ratings"] + document["pairs"]:
            row.update(reason="Declared text is the task output; any quality claims remain solver claims.", evidence=[{"path": evidence["path"], "sha256": evidence["sha256"]}])
        review.freeze_review(packet, document, root / "reviews/ratings", media_root=packet_root)
        mapping = json.loads(next((root / "reviews").glob("*.arm-map.json")).read_text())
        return manifest, results, {"packet": packet, "document": document, "arm_map": mapping}

    def test_validated_notes_process_report_displays_declared_text_with_claims_label(self):
        from skill_bench import private_report
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            packet_root = Path(directory) / "packet"
            manifest, results, bundle = self.notes_fixture(root, packet_root)
            local = private_report.build_local_report(manifest, results, [bundle])
            self.assertIn("text_deliverables", local, "Validated notes-process text deliverables must remain locally inspectable")
            self.assertEqual(len(local["text_deliverables"]), 2)
            self.assertEqual(local["text_deliverables"][0]["name"], "analysis.md")
            self.assertIn("术语解释", local["text_deliverables"][0]["text"])
            destination = Path(directory) / "local"
            private_report.export_local_report(local, destination, media_root=root, packet_roots={bundle["packet"]["review_id"]: packet_root})
            rendered = (destination / "index.html").read_text()
            self.assertIn("Declared text deliverables", rendered)
            self.assertIn("Self-evaluation and explanatory captions remain solver claims", rendered)
            self.assertNotIn("<script>globalThis.fakeQuality=100</script>", rendered)
            self.assertTrue(private_report.validate_local_bundle(destination)["valid"])
            with self.assertRaises(ValueError):
                report.validate_public_bundle(destination)

    def test_v2_text_copies_are_bound_and_artifact_only_views_still_withhold_notes(self):
        from skill_bench import private_report
        for view in ('artifact-only', 'notes-process-v2'):
            with self.subTest(view=view), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'run'
                root.mkdir()
                packet_root = Path(directory) / 'packet'
                manifest, results, bundle = self.notes_fixture(root, packet_root, view=view)
                local = private_report.build_local_report(manifest, results, [bundle])
                self.assertEqual(len(local['text_deliverables']), 0 if view == 'artifact-only' else 2)
                destination = Path(directory) / 'local'
                private_report.export_local_report(local, destination, media_root=root, packet_roots={bundle['packet']['review_id']: packet_root})
                if view == 'artifact-only':
                    self.assertFalse((destination / 'text').exists())
                else:
                    self.assertEqual(len(list((destination / 'text').iterdir())), 1)
                    note = bundle['packet']['entries'][0]['turns'][0]['notes'][0]
                    (packet_root / note['path']).write_text('altered text')
                    with self.assertRaisesRegex(ValueError, 'hash|size'):
                        private_report.export_local_report(local, Path(directory) / 'changed-packet', media_root=root, packet_roots={bundle['packet']['review_id']: packet_root})
                    next((destination / 'text').iterdir()).write_text('altered local text')
                    with self.assertRaisesRegex(ValueError, 'hash|size'):
                        private_report.validate_local_bundle(destination)

    def test_sanitized_v2_text_preserves_raw_source_identity_and_transform_locally(self):
        from skill_bench import private_report, review
        text = 'The sleeve relation is still unclear.\nReproduce with /usr/bin/python3 /home/private/renderer.py.\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            packet_root = Path(directory) / 'packet'
            manifest, results, bundle = self.notes_fixture(root, packet_root, view='notes-process-v2', text=text)
            local = private_report.build_local_report(manifest, results, [bundle])
            note = local['text_deliverables'][0]
            self.assertEqual(note['source_sha256'], hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(note['transformation'], {'id': 'local-path-redaction-v1', 'changed': True})
            self.assertIn('The sleeve relation is still unclear.', note['text'])
            self.assertNotIn('/home/', note['text'])
            destination = Path(directory) / 'local'
            private_report.export_local_report(local, destination, media_root=root, packet_roots={bundle['packet']['review_id']: packet_root})
            data = json.loads((destination / 'report.json').read_text())
            self.assertEqual(data['text_deliverables'][0]['source_sha256'], note['source_sha256'])
            self.assertEqual(data['text_deliverables'][0]['transformation'], note['transformation'])
            self.assertIn('raw source SHA-256', (destination / 'index.html').read_text())
            changed = json.loads(json.dumps(bundle))
            changed['packet']['entries'][0]['turns'][0]['notes'][0]['source_sha256'] = '0' * 64
            changed['arm_map']['packet_sha256'] = review.canonical_hash(changed['packet'])
            with self.assertRaisesRegex(ValueError, 'sealed note'):
                private_report.build_local_report(manifest, results, [changed])

    def test_one_arm_local_screen_hides_comparisons_and_numbers_visible_chapters(self):
        from skill_bench import private_report
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            manifest, results = private_fixture(root)
            manifest['arms'] = [arm for arm in manifest['arms'] if arm['id'] == 'candidate']
            manifest['schedule'] = [row for row in manifest['schedule'] if row['arm'] == 'candidate']
            results = [row for row in results if row['trial_id'] == 'trial-candidate']
            local = private_report.build_local_report(manifest, results)
            rendered = private_report.render_local_html(local)
            self.assertTrue('<section id="version-comparison" hidden>' in rendered, 'A one-arm screen must not display a comparison section')
            self.assertIn('<h2>3. Inspect the case evidence</h2>', rendered)
            self.assertIn('href="#case-evidence">3. Inspect the case evidence', rendered)
            self.assertIn('Tested version', rendered)
            self.assertNotIn('<th scope="row">Candidate versus baseline</th>', rendered)
            self.assertNotIn('<th scope="row">Baseline</th>', rendered)
            self.assertIn('<th scope="row">Tested version</th>', rendered)
            second = Path(directory) / 'second'
            second.mkdir()
            multi_manifest, multi_results = private_fixture(second)
            multi = private_report.render_local_html(private_report.build_local_report(multi_manifest, multi_results))
            self.assertIn('<section id="version-comparison">', multi)
            self.assertIn('<th scope="row">Candidate versus baseline</th>', multi)

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the private layout regression')
    def test_one_version_selector_uses_actual_arm_identity_and_preserves_repeat_runs(self):
        from skill_bench import private_report
        from skill_bench.report_view import LOGIC
        snapshot = 'a' * 64
        commit = 'b' * 40
        data = {'experiment':'history', 'current_experiment':'repeat', 'cohorts':[], 'ratings':[],
            'experiments':[
                {'id':'first','arms':[{'id':'previous','skill_hash':snapshot}]},
                {'id':'repeat','arms':[{'id':'candidate','skill_hash':snapshot}]},
                {'id':'committed','arms':[{'id':'previous','skill_hash':'c'*64}], 'commit_provenance':{'previous_sha':commit}},
                {'id':'unassisted','arms':[{'id':'none','skill_hash':None}]}],
            'trials':[{'experiment':name,'arm':arm} for name,arm in [('first','previous'),('repeat','candidate'),('committed','previous'),('unassisted','none')]]}
        script = private_report._ONE_VERSION_SCRIPT + LOGIC + """
const view=localSingleVersionView(createReportView(data)), state=view.defaults();
const options=view.versionOptions(state);
const first=view.chooseVersions(state,'snapshot:'+'a'.repeat(64),'','first');
const committed=view.chooseVersions(state,'commit:'+'b'.repeat(40),'');
const none=view.chooseVersions(state,'none','');
console.log(JSON.stringify({options,first,committed,none,unknown:view.chooseVersions(state,'snapshot:'+'d'.repeat(64),''),badRun:view.chooseVersions(state,'snapshot:'+'a'.repeat(64),'','committed')}));
"""
        observed = subprocess.run([shutil.which('node'), '-e', "const data=JSON.parse(require('fs').readFileSync(0,'utf8'));" + script], input=json.dumps(data), text=True, capture_output=True, timeout=10, check=True)
        value = json.loads(observed.stdout)
        self.assertEqual(value['options']['candidate']['label'], 'Snapshot '+snapshot)
        self.assertEqual({item['label'] for item in value['options']['candidates']}, {'Snapshot '+snapshot, 'Commit '+commit, 'No skill'})
        self.assertEqual(value['options']['baselines'], [])
        self.assertEqual(value['options']['runs'], ['first','repeat'])
        self.assertEqual(value['first']['experiment'], 'first')
        self.assertEqual(value['committed']['experiment'], 'committed')
        self.assertEqual(value['none']['experiment'], 'unassisted')
        self.assertEqual(value['first']['baseline'], '')
        self.assertIsNone(value['unknown'])
        self.assertIsNone(value['badRun'])

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the private layout regression')
    def test_one_arm_chart_removal_handles_already_numbered_headings(self):
        from skill_bench import private_report
        # Earlier rendering can number headings before the local layout adapter runs.
        setup = """
const removed=[];
const panels=['Comparison by case','2.2. Comparison by case','2.1. Runs by tested version'].map(text=>({querySelector:()=>({textContent:text,dataset:{}}),remove:()=>removed.push(text)}));
const document={getElementById:()=>({querySelectorAll:()=>panels})},helpDefinitions=new Map();
"""
        script = setup + private_report._ONE_VERSION_SCRIPT + "applySingleVersionLayout();console.log(JSON.stringify(removed));"
        observed = subprocess.run([shutil.which('node'), '-e', script], text=True, capture_output=True, timeout=10, check=True)
        self.assertEqual(json.loads(observed.stdout), ['Comparison by case', '2.2. Comparison by case'])

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for source-bound evidence projection')
    def test_local_atom_rules_and_single_version_slots_preserve_frozen_case_identity(self):
        from skill_bench import private_report
        from skill_bench.report_view import LOGIC
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            manifest, results = private_fixture(root)
            atom = manifest['cases'][0]['atoms'][0]
            atom.update(criterion='The contour follows a shared alignment edge.', anchors={'0': 'Broken relation', '1': 'Partly aligned', '2': 'Aligned relation'})
            local = private_report.build_local_report(manifest, results)
            self.assertEqual(local['case_contexts'][0]['case_fingerprint'], report.canonical_hash(manifest['cases'][0]))
            self.assertEqual(local['case_contexts'][0]['case_fingerprint'], local['cohorts'][0]['case_fingerprint'])
            script = private_report._ONE_VERSION_SCRIPT + private_report._local_script(LOGIC) + "const view=createReportView(data),trial=data.trials[0],state={...view.defaults(),review_view:''},context=view.contextFor(trial);const projection=view.evidenceRows(state,localVersionSlots([trial],''),1,context);console.log(JSON.stringify({slots:localVersionSlots([trial],'').map(s=>s.arm),rule:projection.atoms[0].definition.criterion,anchors:projection.atoms[0].definition.anchors,outputs:projection.outputs.map(row=>row.name)}));"
            observed = subprocess.run([shutil.which('node'), '-e', "const fs=require('fs');const data=JSON.parse(fs.readFileSync(0,'utf8'));" + script], input=json.dumps(local), text=True, capture_output=True, timeout=10, check=True)
            value = json.loads(observed.stdout)
            self.assertEqual(value['slots'], ['previous'])
            self.assertEqual(value['rule'], atom['criterion'])
            self.assertEqual(value['anchors'], atom['anchors'])
            self.assertEqual(value['outputs'], ['drawing.png'])

    def test_independent_capture_frames_remain_in_proofs_with_human_readable_time_labels(self):
        from skill_bench import private_report, review
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            manifest, results = private_fixture(root)
            declaration = {'path': 'index.html', 'kind': 'editable', 'format': 'html'}
            manifest['cases'][0]['turns'][0]['artifacts'].append(declaration)
            image = root / 'verifier/frame-23.png'
            image.parent.mkdir()
            image.write_bytes(pixel_png(171))
            for result in results:
                source = root / 'trials' / result['trial_id'] / 'turn1/artifacts/index.html'
                source.write_text('<!doctype html><p>Frozen study</p>')
                source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                result['turns'][0]['artifacts'].append({**declaration, 'snapshot': 'turn1/artifacts/index.html', 'sha256': source_hash, 'size': source.stat().st_size})
                result['turns'][0]['source_verification'] = [{'source_sha256': source_hash, 'format': 'html', 'source_reopen_verified': True, 'source_editability_verified': False, 'generated_code_executed': True, 'rendered': {'frame-23': {'path': 'verifier/frame-23.png', 'sha256': hashlib.sha256(image.read_bytes()).hexdigest(), 'size': image.stat().st_size, 'label': 'desktop-22-15000ms', 'profile': 'desktop', 'time_ms': 15041.2, 'requested_time_ms': 15000}}}]
                path = root / 'trials' / result['trial_id'] / 'result.json'
                path.write_text(json.dumps(result))
                seal_result(path)
            destination = Path(directory) / 'packet'
            with mock.patch('skill_bench.experiment.load_experiment', return_value=manifest):
                packet = review.export_review(root, destination, seed=3, allow_private=True)
            document = json.loads((destination / 'ratings-template.json').read_text())
            document['reviewer'].update(id='capture-fixture', **{'class': 'human'})
            evidence = packet['entries'][0]['turns'][0]['status_evidence']
            for row in document['ratings'] + document['pairs']:
                row.update(reason='Only the declared sampled capture scope is supported.', evidence=[{'path': evidence['path'], 'sha256': evidence['sha256']}])
            mapping = json.loads((root / 'reviews' / (packet['review_id'] + '.arm-map.json')).read_text())
            local = private_report.build_local_report(manifest, results, [{'packet': packet, 'document': document, 'arm_map': mapping}])
            capture_hash = hashlib.sha256(image.read_bytes()).hexdigest()
            captures = [item for item in local['media'] if item['sha256'] == capture_hash]
            self.assertTrue(captures)
            self.assertTrue(all(item['kind'] == 'independent-capture' for item in captures))
            self.assertTrue(all('desktop-22-15000ms' in item['name'] for item in captures))
            self.assertTrue(any(item.get('time_ms') == 15041.2 for item in captures))
            output = Path(directory) / 'local'
            private_report.export_local_report(local, output, media_root=root, packet_roots={packet['review_id']: destination})
            self.assertTrue(private_report.validate_local_bundle(output)['valid'])

    def test_private_context_and_real_rasters_are_visible_only_in_local_bundle(self):
        from skill_bench import private_report
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest, results = private_fixture(root)
            public = report.build_report(manifest, results)
            self.assertEqual(public["media"], [])
            self.assertNotIn("Preserve the curved", json.dumps(public))
            self.assertTrue(callable(getattr(private_report, "build_local_report", None)), "Local-private reports must preserve inspectable context and evidence")
            local = private_report.build_local_report(manifest, results)
            destination = Path(directory) / "local"
            private_report.export_local_report(local, destination, media_root=root)
            data = json.loads((destination / "report.json").read_text())
            self.assertEqual(data["kind"], "skill-benchmark-local-report")
            self.assertEqual(data["visibility"], "local-private")
            self.assertEqual(data["case_contexts"][0]["visibility"], "local-private")
            self.assertIn("Preserve the curved", json.dumps(data))
            self.assertEqual({image["kind"] for image in data["media"]}, {"reference", "preview"})
            self.assertEqual(len(data["media"]), 3)
            self.assertTrue(private_report.validate_local_bundle(destination)["valid"])
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
            self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in destination.rglob("*") if path.is_file()))
            self.assertNotIn("private-session", json.dumps(data))
            self.assertNotIn("data:image/", (destination / "index.html").read_text())
            with self.assertRaises(ValueError):
                report.validate_public_bundle(destination)
            with self.assertRaises(ValueError):
                report.export_report(local, Path(directory) / "accidental-public", media_root=root)
            from skill_bench.publication import combine_public_reports
            with self.assertRaises(ValueError):
                combine_public_reports([destination])
            data["kind"] = "skill-benchmark-report"
            (destination / "report.json").write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                report.validate_public_bundle(destination)

    def test_local_export_checks_hashes_byte_limits_permissions_and_output_location(self):
        from skill_bench import private_report
        for failure in ("hash", "size", "total", "git", "symlink"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "run"
                root.mkdir()
                manifest, results = private_fixture(root)
                data = private_report.build_local_report(manifest, results)
                destination = Path(directory) / "local"
                options = {}
                if failure == "hash":
                    (root / "reference.png").write_bytes(pixel_png(5))
                elif failure == "size":
                    options["max_file_bytes"] = 1
                elif failure == "total":
                    options["max_total_bytes"] = 1
                elif failure == "git":
                    parent = Path(directory) / "repo"
                    parent.mkdir()
                    (parent / ".git").mkdir()
                    destination = parent / "local"
                else:
                    link = Path(directory) / "link"
                    link.symlink_to(root, target_is_directory=True)
                    destination = link / "local"
                with self.assertRaises(ValueError):
                    private_report.export_local_report(data, destination, media_root=root, **options)
                self.assertFalse(destination.exists())

    def test_local_validator_rejects_extra_files_tampered_rasters_and_open_permissions(self):
        from skill_bench import private_report
        for failure in ("extra", "image", "permissions"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "run"
                root.mkdir()
                manifest, results = private_fixture(root)
                destination = Path(directory) / "local"
                private_report.export_local_report(private_report.build_local_report(manifest, results), destination, media_root=root)
                if failure == "extra":
                    (destination / "source.py").write_text("private program")
                elif failure == "image":
                    next((destination / "media").iterdir()).write_bytes(pixel_png(7))
                else:
                    (destination / "report.json").chmod(0o644)
                with self.assertRaises(ValueError):
                    private_report.validate_local_bundle(destination)

    def test_original_frozen_review_reasons_survive_without_exporting_arm_maps(self):
        from skill_bench import private_report, review
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest, results = private_fixture(root)
            packet_root = Path(directory) / "packet"
            with mock.patch("skill_bench.experiment.load_experiment", return_value=manifest):
                packet = review.export_review(root, packet_root, seed=3, allow_private=True)
            document = json.loads((packet_root / "ratings-template.json").read_text())
            document["reviewer"].update(id="human-fixture", **{"class": "human"})
            artifact = packet["entries"][0]["turns"][0]["artifacts"][0]
            evidence = [{"path": artifact["path"], "sha256": artifact["sha256"]}]
            for rating in document["ratings"]:
                rating.update(score=2, reason="The observed contour is continuous.", evidence=evidence)
            for pair in document["pairs"]:
                pair.update(outcome="tie", reason="Both preserve the observed contour.", evidence=evidence)
            frozen = review.freeze_review(packet, document, root / "reviews/ratings", media_root=packet_root)
            from skill_bench.cli import frozen_rating
            record = frozen_rating(root, Path(frozen["path"]))
            mapping = json.loads(next((root / "reviews").glob("*.arm-map.json")).read_text())
            bundle = {"packet": packet, "document": record["review"], "arm_map": mapping}
            local = private_report.build_local_report(manifest, results, [bundle])
            self.assertEqual(local["ratings"][0]["reason"], "The observed contour is continuous.")
            self.assertEqual(local["pairs"][0]["reason"], "Both preserve the observed contour.")
            destination = Path(directory) / "local"
            private_report.export_local_report(local, destination, media_root=root, packet_roots={packet["review_id"]: packet_root})
            serialized = (destination / "report.json").read_text()
            self.assertNotIn(mapping["private_key"], serialized)
            self.assertFalse(any("arm-map" in path.name for path in destination.rglob("*")))
            self.assertEqual(len(list((destination / "media").iterdir())), 3)

    def test_local_command_never_executes_models_and_rejects_unfrozen_ratings(self):
        from skill_bench import cli
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest, results = private_fixture(root)
            destination = Path(directory) / "local"
            with mock.patch.object(cli, "load_experiment", return_value=manifest), mock.patch.object(cli, "load_results", return_value=results), mock.patch.object(cli, "run_experiment", side_effect=AssertionError("Model execution is forbidden")), mock.patch("builtins.print"):
                self.assertEqual(cli.main(["local-report", "--run", str(root), "--output", str(destination)]), 0)
                self.assertEqual(cli.main(["local-report", "--run", str(root), "--output", str(Path(directory) / "bad"), "--ratings", str(root / "draft.json")]), 2)
            self.assertTrue(destination.is_dir())

    def test_local_command_preserves_frozen_rating_and_media_integrity_gates(self):
        from skill_bench import cli, review
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest, results = private_fixture(root)
            packet_root = Path(directory) / "packet"
            with mock.patch("skill_bench.experiment.load_experiment", return_value=manifest):
                packet = review.export_review(root, packet_root, seed=9, allow_private=True)
            document = json.loads((packet_root / "ratings-template.json").read_text())
            document["reviewer"].update(id="human-fixture", **{"class": "human"})
            image = packet["entries"][0]["turns"][0]["artifacts"][0]
            for row in document["ratings"]:
                row.update(reason="The observed image is insufficient for this requirement.", evidence=[{"path": image["path"], "sha256": image["sha256"]}])
            for row in document["pairs"]:
                row.update(reason="The observed images do not establish a preference.", evidence=[{"path": image["path"], "sha256": image["sha256"]}])
            frozen = review.freeze_review(packet, document, root / "reviews/ratings", media_root=packet_root)
            rating_path = Path(frozen["path"])
            with mock.patch.object(cli, "load_experiment", return_value=manifest), mock.patch.object(cli, "load_results", return_value=results), mock.patch("builtins.print"):
                def run_export(name, rating=rating_path):
                    return cli.main(["local-report", "--run", str(root), "--output", str(Path(directory) / name), "--review-packet", str(packet_root), "--ratings", str(rating)])
                self.assertEqual(run_export("valid"), 0)
                data = json.loads((Path(directory) / "valid/report.json").read_text())
                self.assertEqual(data["review_bindings"][0]["rating_sha256"], review.canonical_hash(document))
                draft = root / "reviews/ratings/draft.json"
                draft.write_text(json.dumps(document))
                self.assertEqual(run_export("draft", draft), 2)
                tampered = json.loads(rating_path.read_text())
                tampered["review"]["ratings"][0]["score"] = 1
                corrupt = root / "reviews/ratings/corrupt.json"
                corrupt.write_text(json.dumps(tampered))
                self.assertEqual(run_export("corrupt", corrupt), 2)
                (packet_root / image["path"]).write_bytes(pixel_png(15))
                self.assertEqual(run_export("changed-media"), 2)
            self.assertTrue(all(not (Path(directory) / name).exists() for name in ("draft", "corrupt", "changed-media")))

    def test_declared_task_text_is_redacted_and_source_playback_metadata_is_retained(self):
        from skill_bench import private_report
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest, results = private_fixture(root)
            manifest["cases"][0]["turns"][0]["prompt"] += " Source /home/private/sketch.png; session 12345678-1234-4234-8234-123456789abc.\napi_key = SECRET"
            data = private_report.build_local_report(manifest, results)
            prompt = data["case_contexts"][0]["turns"][0]["prompt"]
            self.assertNotIn("/home/", prompt)
            self.assertNotIn("12345678", prompt)
            self.assertNotIn("SECRET", prompt)
            self.assertIn("Preserve the curved", prompt)
            case = manifest["cases"][0]
            case["turns"][0]["artifacts"].append({"path": "scene.html", "kind": "editable", "format": "html"})
            turn = results[0]["turns"][0]
            turn["artifacts"].append({"path": "scene.html", "kind": "editable", "sha256": "a" * 64})
            playback = {"scenario": {"action_count": 3, "effect_observed": True}, "audio": {"known_input": True, "fallback_observed": False}}
            turn["source_verification"] = [{"format": "html", "source_sha256": "a" * 64, "source_reopen_verified": True, "scope": "Independent playback with recorded action and audio inputs.", "playback": playback}]
            local = private_report.build_local_report(manifest, results)
            proof = next(trial for trial in local["trials"] if trial["id"] == results[0]["trial_id"])["turns"][0]["source_proofs"][0]
            self.assertEqual(proof["playback"], playback)
            self.assertNotIn("scene.html", {item.get("name") for item in local["media"]})

    @unittest.skipUnless(shutil.which("node"), "Node is needed for trusted renderer logic checks")
    def test_private_references_require_both_explicit_local_identity_markers(self):
        from skill_bench import private_report
        from skill_bench.report_view import LOGIC
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest, results = private_fixture(root)
            destination = Path(directory) / "local"
            private_report.export_local_report(private_report.build_local_report(manifest, results), destination, media_root=root)
            data = json.loads((destination / "report.json").read_text())
            script = "const view=createReportView(data);const trial=data.trials[0];const allowed=view.referencesFor(trial,1).length;data.kind='skill-benchmark-report';const publicKind=view.referencesFor(trial,1).length;data.kind='skill-benchmark-local-report';data.visibility='public';console.log(JSON.stringify({allowed,publicKind,publicVisibility:view.referencesFor(trial,1).length}));"
            observed = subprocess.run([shutil.which("node"), "-e", "const fs=require('fs');const data=JSON.parse(fs.readFileSync(0,'utf8'));" + private_report._local_script(LOGIC) + script], input=json.dumps(data), text=True, capture_output=True, timeout=10, check=True)
            self.assertEqual(json.loads(observed.stdout), {"allowed": 1, "publicKind": 0, "publicVisibility": 0})


if __name__ == "__main__":
    unittest.main()
