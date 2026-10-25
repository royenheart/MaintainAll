"""Acceptance checks for anonymous review and immutable ratings."""
import hashlib
import io
import json
import shutil
import struct
import tempfile
import unittest
from unittest import mock
from pathlib import Path
import zlib
from skill_bench import review
from skill_bench.store import append_event

def pixel_png(red=0):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes([0, red, 0, 0]))) + chunk(b"IEND", b"")

PNG = pixel_png()

def fixture(root):
    cases = [{"id": "case-a", "version": "1", "atoms": [{"id": "relation", "active_turns": [1], "dimension": "construction"}], "attachments": []}]
    manifest = {"schema_version": 1, "id": "experiment", "model": "model", "effort": "low", "backend": "test", "fingerprint": "experiment-fingerprint", "cases": cases, "arms": [{"id": "previous"}, {"id": "candidate"}], "schedule": []}
    for arm in ("previous", "candidate"):
        trial = "trial-" + arm
        manifest["schedule"].append({"trial_id": trial, "case_id": "case-a", "arm": arm, "repeat": 1})
        path = root / "trials" / trial / "turn1" / "artifacts" / "drawing.png"
        path.parent.mkdir(parents=True)
        path.write_bytes(pixel_png(20 if arm == "previous" else 80))
        data = path.read_bytes()
        result = {"trial_id": trial, "status": "completed", "thread_id": "private-session", "turns": [{"turn": 1, "status": "completed", "thread_id": "private-session", "artifacts": [{"path": "drawing.png", "snapshot": str(path.relative_to(root / "trials" / trial)), "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}], "seconds": 1, "usage": {"input_tokens": 3, "cached_input_tokens": 1, "uncached_input_tokens": 2, "output_tokens": 1}, "delivery": {"passed": True}}]}
        (root / "trials" / trial / "result.json").write_text(json.dumps(result))
    (root / "manifest.json").write_text(json.dumps(manifest))
    for result_path in root.glob("trials/*/result.json"):
        seal_result(result_path)
    return manifest

def seal_result(path):
    path.with_name("result-seal.json").write_text(json.dumps({"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))

class ReviewTests(unittest.TestCase):
    def setUp(self):
        # Focused fixtures mock only the full experiment schema gate. Real result
        # seals, artifact inventories and export checks remain active.
        self.manifest_gate = mock.patch("skill_bench.experiment.load_experiment", side_effect=lambda root: json.loads((Path(root) / "manifest.json").read_text()))
        self.manifest_gate.start()
        self.addCleanup(self.manifest_gate.stop)

    def test_new_failure_scope_withholds_stale_files_and_requires_unknown_ratings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            fixture(root)
            for path in root.glob('trials/*/result.json'):
                result = json.loads(path.read_text())
                result.update(status='failed', backend={'id': 'local_codex'})
                turn = result['turns'][0]
                turn['status'] = 'failed'
                turn['source_verification'] = [{'rendered': {'source': {'path': 'unused-proof.png', 'sha256': '4' * 64, 'size': 50}}}]
                log = path.parent / 'turn-1/events.jsonl'
                log.parent.mkdir()
                log.write_text('{"type":"turn.started"}\n{"type":"turn.failed","error":{"message":"Discovery connection failed"}}\n')
                path.write_text(json.dumps(result))
                seal_result(path)
            packet = review.export_review(root, Path(directory) / 'packet', seed=918, selected_cases=['case-a'], evidence_scope='failed-turn-v1')
            self.assertEqual(packet['evidence_scope'], 'failed-turn-v1')
            for entry in packet['entries']:
                turn = entry['turns'][0]
                self.assertEqual(turn['evidence_status'], 'failed-no-model-output')
                self.assertEqual(turn['artifacts'], [])
                self.assertEqual(len(turn['persisted_artifact_inventory']), 1)
                self.assertEqual(len(turn['persisted_source_proof_inventory']), 1)
                self.assertNotIn('drawing.png', json.dumps(turn['persisted_artifact_inventory']))
            template = json.loads((Path(directory) / 'packet/ratings-template.json').read_text())
            template['reviewer'].update(id='failure-review', **{'class': 'human'})
            for row in template['ratings'] + template['pairs']:
                turn = packet['entries'][0]['turns'][0]
                row.update(reason='No new model output was observed.', evidence=[{'path': turn['status_evidence']['path'], 'sha256': turn['status_evidence']['sha256']}])
            review.validate_review(packet, template, media_root=Path(directory) / 'packet')
            template['ratings'][0]['score'] = 2
            with self.assertRaisesRegex(ValueError, 'unverifiable'):
                review.validate_review(packet, template)

    def test_new_failure_scope_preserves_partial_output_and_missing_log_stays_unknown(self):
        for event, expected in [('{"type":"item.completed","item":{"type":"agent_message","text":"Working on it"}}\n', 'partial-model-output'), ('', 'unknown-failed-output')]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'run'
                root.mkdir()
                fixture(root)
                for path in root.glob('trials/*/result.json'):
                    result = json.loads(path.read_text())
                    result.update(status='failed', backend={'id': 'local_codex'})
                    result['turns'][0]['status'] = 'failed'
                    if event:
                        log = path.parent / 'turn-1/events.jsonl'
                        log.parent.mkdir()
                        log.write_text(event)
                    path.write_text(json.dumps(result))
                    seal_result(path)
                packet = review.export_review(root, Path(directory) / 'packet', seed=919, evidence_scope='failed-turn-v1')
                self.assertTrue(all(entry['turns'][0]['evidence_status'] == expected for entry in packet['entries']))
                self.assertTrue(all(entry['turns'][0]['artifacts'] for entry in packet['entries']))

    def test_export_is_anonymous_reproducible_and_real_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            fixture(root)
            packet = review.export_review(root, Path(directory) / "packet", seed=12)
            self.assertEqual(len(packet.get("entries", [])), 2)
            payload = json.dumps(packet)
            self.assertNotIn("private-session", payload)
            self.assertNotIn("trial-candidate", payload)
            self.assertNotIn('"arm"', payload)
            self.assertEqual(len(packet["pairs"]), 1)
            for entry in packet["entries"]:
                item = entry["turns"][0]["artifacts"][0]
                self.assertEqual(hashlib.sha256((Path(directory) / "packet" / item["path"]).read_bytes()).hexdigest(), item["sha256"])

    def test_anonymous_ids_require_private_key_and_reproduce_only_with_same_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            fixture(root)
            packet = review.export_review(root, Path(directory) / "packet", seed=12)
            predicted = {review.canonical_hash({"review": packet["review_id"], "trial": row["trial_id"]})[:16] for row in json.loads((root / "manifest.json").read_text())["schedule"]}
            actual = {entry["id"] for entry in packet["entries"]}
            self.assertTrue(actual.isdisjoint(predicted))
            private = json.loads(next((root / "reviews").glob("*.arm-map.json")).read_text())
            key_path = root / "reviews/blind-key.json"
            self.assertEqual(key_path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(private["private_key"], json.dumps(packet))
            self.assertEqual(private["packet_sha256"], review.canonical_hash(packet))
            review.validate_packet_mapping(packet, private)
            changed = json.loads(json.dumps(packet))
            changed["entries"][0]["atoms"] = []
            with self.assertRaisesRegex(ValueError, "packet fingerprint"):
                review.validate_packet_mapping(changed, private)
            for entry_id, mapped in private["entries"].items():
                self.assertEqual(entry_id, review.blind_entry_id(packet["review_id"], mapped["trial_id"], private["private_key"]))
            copied = Path(directory) / "same-key"
            shutil.copytree(root, copied)
            next((copied / "reviews").glob("*.arm-map.json")).unlink()
            repeat = review.export_review(copied, Path(directory) / "repeat", seed=12)
            self.assertEqual(packet, repeat)
            fresh = Path(directory) / "fresh"
            fresh.mkdir()
            fixture(fresh)
            different = review.export_review(fresh, Path(directory) / "different-key", seed=12)
            self.assertTrue(actual.isdisjoint({entry["id"] for entry in different["entries"]}))

    def test_traversal_symlink_oversize_and_hash_mismatch_are_rejected(self):
        for bad in ("traversal", "symlink", "oversize", "hash"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "run"
                root.mkdir()
                fixture(root)
                result_path = root / "trials" / "trial-previous" / "result.json"
                result = json.loads(result_path.read_text())
                artifact = result["turns"][0]["artifacts"][0]
                if bad == "traversal":
                    artifact["snapshot"] = "../outside.png"
                elif bad == "symlink":
                    path = root / "trials" / "trial-previous" / artifact["snapshot"]
                    outside = Path(directory) / "outside.png"
                    outside.write_bytes(path.read_bytes())
                    path.unlink()
                    path.symlink_to(outside)
                elif bad == "hash":
                    artifact["sha256"] = "0" * 64
                result_path.write_text(json.dumps(result))
                seal_result(result_path)
                with self.assertRaises((ValueError, FileNotFoundError)):
                    review.export_review(root, Path(directory) / "packet", seed=12, max_file_bytes=2 if bad == "oversize" else 8388608)
                self.assertFalse((Path(directory) / "packet").exists())

    def test_signature_only_png_without_pixels_is_withheld_with_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            fixture(root)
            result_path = root / "trials/trial-previous/result.json"
            result = json.loads(result_path.read_text())
            artifact = result["turns"][0]["artifacts"][0]
            source = result_path.parent / artifact["snapshot"]
            source.write_bytes(b"\x89PNG\r\n\x1a\nwithout pixel data")
            artifact.update(size=source.stat().st_size, sha256=hashlib.sha256(source.read_bytes()).hexdigest())
            result.update(status="failed")
            result["turns"][0]["delivery"] = {"delivery_pass": False}
            result_path.write_text(json.dumps(result))
            seal_result(result_path)
            packet = review.export_review(root, Path(directory) / "packet", seed=20)
            withheld = [item for entry in packet["entries"] for turn in entry["turns"] for item in turn.get("withheld_previews", [])]
            self.assertEqual(len(withheld), 1)
            self.assertEqual(withheld[0]["sha256"], artifact["sha256"])
            self.assertIn("PNG", withheld[0]["withheld_reason"])
            self.assertEqual(sum(len(turn["artifacts"]) for entry in packet["entries"] for turn in entry["turns"]), 1)

    def test_private_reference_is_not_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest = fixture(root)
            manifest["cases"][0]["assets"] = [{"id": "personal", "visibility": "private", "snapshot": "unavailable-private.png"}]
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Private cases"):
                review.export_review(root, Path(directory) / "packet", seed=12)

    def test_closed_partial_run_preserves_missing_turns_as_unknown_status_evidence(self):
        for attempted in (False, True):
            with self.subTest(attempted=attempted), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "run"
                root.mkdir()
                manifest = fixture(root)
                manifest["cases"][0]["turns"] = [{"prompt": "Inspect turn " + str(number), "artifacts": []} for number in (1, 2, 3)]
                manifest["cases"][0]["atoms"][0]["active_turns"] = [1, 2, 3]
                (root / "manifest.json").write_text(json.dumps(manifest))
                missing = root / "trials/trial-candidate"
                (missing / "result.json").unlink()
                (missing / "result-seal.json").unlink()
                append_event(root, {"type": "run_started"})
                if attempted:
                    append_event(root, {"type": "call_reserved", "trial_id": "trial-candidate", "turn": 1}, 12)
                append_event(root, {"type": "run_finished", "reason": "wall_clock_budget_exhausted"})
                destination = Path(directory) / "packet"
                packet = review.export_review(root, destination, seed=12)
                entry = next(item for item in packet["entries"] if item.get("result_record") == "missing")
                self.assertEqual(entry["status"], "interrupted" if attempted else "not_attempted")
                self.assertEqual([turn["turn"] for turn in entry["turns"]], [1, 2, 3])
                for turn in entry["turns"]:
                    self.assertEqual(turn["artifacts"], [])
                    evidence = turn["status_evidence"]
                    payload = (destination / evidence["path"]).read_bytes()
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), evidence["sha256"])
                    self.assertEqual(json.loads(payload)["reservation_observed"], attempted)
                document = json.loads((destination / "ratings-template.json").read_text())
                document["reviewer"]["id"] = "independent-reviewer"
                for rating in document["ratings"]:
                    origin = next(item for item in packet["entries"] if item["id"] == rating["entry"])
                    turn = next(item for item in origin["turns"] if item["turn"] == rating["turn"])
                    rating.update(reason="No observable outcome for this planned turn.", evidence=[{key: turn["status_evidence"][key] for key in ("path", "sha256")}])
                document["pairs"][0].update(reason="One planned arm has no sealed outcome.", evidence=[{key: entry["turns"][0]["status_evidence"][key] for key in ("path", "sha256")}])
                review.validate_review(packet, document, media_root=destination)
                unavailable = next(row for row in document["ratings"] if row["entry"] == entry["id"])
                unavailable["score"] = 0
                with self.assertRaisesRegex(ValueError, "unverifiable"):
                    review.validate_review(packet, document, media_root=destination)
                unavailable["score"] = "unverifiable"
                document["pairs"][0]["outcome"] = "win"
                with self.assertRaisesRegex(ValueError, "undetermined"):
                    review.validate_review(packet, document, media_root=destination)

    def test_live_missing_unsealed_existing_or_forged_ledger_cannot_export(self):
        for fault in ("live", "unsealed", "ledger-tamper", "execution-after-close"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "run"
                root.mkdir()
                fixture(root)
                trial = root / "trials/trial-candidate"
                if fault != "unsealed":
                    (trial / "result.json").unlink()
                (trial / "result-seal.json").unlink()
                append_event(root, {"type": "run_started"})
                if fault != "live":
                    append_event(root, {"type": "run_finished", "reason": "wall_clock_budget_exhausted"})
                if fault == "ledger-tamper":
                    ledger = root / "events.jsonl"
                    ledger.write_text(ledger.read_text().replace("run_finished", "run_finished_forged"))
                if fault == "execution-after-close":
                    append_event(root, {"type": "turn_started", "trial_id": "trial-candidate", "turn": 1})
                with self.assertRaises(ValueError):
                    review.export_review(root, Path(directory) / "packet", seed=12)
                self.assertFalse((Path(directory) / "packet").exists())

    def test_notes_are_opt_in_and_arm_or_credentials_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest = fixture(root)
            manifest["cases"][0]["turns"] = [{"prompt": "Explain the drawing.", "artifacts": [{"path": "notes.md", "kind": "notes", "format": "md"}]}]
            (root / "manifest.json").write_text(json.dumps(manifest))
            result_path = root / "trials" / "trial-previous" / "result.json"
            result = json.loads(result_path.read_text())
            note = root / "trials" / "trial-previous" / "notes.md"
            note.write_text("candidate wins. API_KEY=secret")
            result["turns"][0]["artifacts"].append({"path": "notes.md", "snapshot": "notes.md", "kind": "notes", "review_safe": True, "size": note.stat().st_size, "sha256": hashlib.sha256(note.read_bytes()).hexdigest()})
            result_path.write_text(json.dumps(result))
            seal_result(result_path)
            packet = review.export_review(root, Path(directory) / "artifact", seed=12)
            self.assertNotIn("secret", json.dumps(packet))
            with self.assertRaisesRegex(ValueError, "private or arm"):
                review.export_review(root, Path(directory) / "notes", seed=12, view="notes-process")

    def test_process_notes_use_frozen_case_declarations_not_solver_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest = fixture(root)
            manifest["cases"][0]["turns"] = [{"prompt": "Explain the drawing.", "artifacts": [{"path": "notes.md", "kind": "notes", "format": "md"}, {"path": "legacy.md", "kind": "notes", "format": "md"}]}]
            (root / "manifest.json").write_text(json.dumps(manifest))
            result_path = root / "trials/trial-previous/result.json"
            result = json.loads(result_path.read_text())
            for name, text, flags in [("notes.md", "The previous selected A direction uses <b>quiet space</b>; the candidate direction tightens alignment.", {}), ("legacy.md", "Excluded legacy statement.", {"review_safe": False}), ("undeclared.md", "Excluded solver statement.", {"kind": "notes", "review_safe": True})]:
                path = result_path.parent / name
                path.write_text(text)
                result["turns"][0]["artifacts"].append({"path": name, "snapshot": name, "size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **flags})
            result_path.write_text(json.dumps(result))
            seal_result(result_path)
            artifact_packet = review.export_review(root, Path(directory) / "artifacts", seed=13)
            self.assertNotIn("quiet space", json.dumps(artifact_packet))
            destination = Path(directory) / "process"
            process_packet = review.export_review(root, destination, seed=13, view="notes-process")
            notes = [note for entry in process_packet["entries"] for turn in entry["turns"] for note in turn.get("notes", [])]
            self.assertEqual(len(notes), 1)
            self.assertEqual((notes[0]["name"], notes[0]["kind"], notes[0]["format"]), ("notes.md", "notes", "md"))
            self.assertNotIn("Excluded", json.dumps(process_packet))
            self.assertIn("&lt;b&gt;quiet space&lt;/b&gt;", (destination / "index.html").read_text())

    def test_contextual_arm_labels_and_private_note_values_are_rejected(self):
        for text in ("skill version: candidate", "arm=previous", "candidate wins", "baseline none", "版本 candidate", "API_KEY=secret", "Authorization: Bearer secret", "Bearer secret", "/home/private/workspace", "12345678-1234-4234-8234-123456789abc"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "private or arm"):
                review._safe_text(text, ["none", "previous", "candidate"])

    def test_review_ratings_require_full_evidence_and_freeze_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            fixture(root)
            dest = Path(directory) / "packet"
            packet = review.export_review(root, dest, seed=12)
            document = json.loads((dest / "ratings-template.json").read_text())
            document["reviewer"]["id"] = "reviewer-a"
            for row in document["ratings"]:
                entry = next(e for e in packet["entries"] if e["id"] == row["entry"])
                artifact = entry["turns"][0]["artifacts"][0]
                row.update(score=2, evidence=[{"path": artifact["path"], "sha256": artifact["sha256"]}], reason="Visible connected relation.")
            artifact = packet["entries"][0]["turns"][0]["artifacts"][0]
            document["pairs"][0].update(outcome="tie", evidence=[{"path": artifact["path"], "sha256": artifact["sha256"]}], reason="Both directions meet the same stated relation.")
            summary = review.validate_review(packet, document, media_root=dest)
            self.assertIsNone(summary["automatic_quality_pass"])
            frozen = review.freeze_review(packet, document, Path(directory) / "ratings", media_root=dest)
            with self.assertRaises(FileExistsError):
                review.freeze_review(packet, document, Path(directory) / "ratings", media_root=dest)
            stored = json.loads(Path(frozen["path"]).read_text())
            self.assertTrue(stored["frozen"])
            for bad in ("duplicate", "missing", "hash", "reason", "boolean", "self-score"):
                broken = json.loads(json.dumps(document))
                if bad == "duplicate":
                    broken["ratings"].append(broken["ratings"][0])
                elif bad == "missing":
                    broken["ratings"].pop()
                elif bad == "hash":
                    broken["ratings"][0]["evidence"][0]["sha256"] = "0" * 64
                elif bad == "reason":
                    broken["ratings"][0]["reason"] = ""
                elif bad == "boolean":
                    broken["ratings"][0]["score"] = True
                else:
                    broken["reviewer"]["class"] = "model-self-assessment"
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    review.validate_review(packet, broken, media_root=dest)

    def test_actual_manifest_and_result_seals_are_required_before_mapping_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            fixture(root)
            (root / "manifest-seal.json").write_text(json.dumps({"sha256": "0" * 64}))
            self.manifest_gate.stop()
            with self.assertRaisesRegex(ValueError, "manifest seal"):
                review.export_review(root, Path(directory) / "packet", seed=1)
            self.manifest_gate.start()
            seal = root / "trials/trial-previous/result-seal.json"
            seal.write_text(json.dumps({"sha256": "0" * 64}))
            with self.assertRaisesRegex(ValueError, "result seal"):
                review.export_review(root, Path(directory) / "packet", seed=1)
            self.assertFalse((root / "reviews").exists())

    def test_explicit_private_review_keeps_original_reference_local(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest = fixture(root)
            original = root / "private.png"
            original.write_bytes(PNG)
            manifest["cases"][0]["assets"] = [{"id":"original", "visibility":"private", "path":"private.png", "sha256":hashlib.sha256(PNG).hexdigest(), "size":len(PNG)}]
            (root / "manifest.json").write_text(json.dumps(manifest))
            dest = Path(directory) / "private-packet"
            packet = review.export_review(root, dest, seed=2, allow_private=True)
            self.assertEqual(packet["privacy"], "local-private")
            self.assertEqual(len(packet["references"]), 1)
            self.assertEqual(dest.stat().st_mode & 0o777, 0o700)

    def test_declared_names_match_rubric_evidence_without_exposing_model_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            root.mkdir()
            manifest = fixture(root)
            manifest["cases"][0]["turns"] = [{"prompt":"Inspect the drawing.", "artifacts":[{"path":"drawing.png"}]}]
            manifest["cases"][0]["atoms"][0]["evidence"] = {"required_artifacts":["drawing.png"]}
            (root / "manifest.json").write_text(json.dumps(manifest))
            result_path = root / "trials/trial-previous/result.json"
            result = json.loads(result_path.read_text())
            extra = root / "trials/trial-previous/model-arbitrary-identifier.png"
            extra.write_bytes(PNG)
            result["turns"][0]["artifacts"].append({"path":extra.name,"snapshot":extra.name,"size":len(PNG),"sha256":hashlib.sha256(PNG).hexdigest()})
            result_path.write_text(json.dumps(result))
            seal_result(result_path)
            dest = Path(directory) / "packet"
            packet = review.export_review(root, dest, seed=7)
            names = [item["name"] for entry in packet["entries"] for turn in entry["turns"] for item in turn["artifacts"]]
            self.assertEqual(names.count("drawing.png"), 2)
            self.assertEqual(names.count("additional-preview"), 1)
            self.assertNotIn("model-arbitrary-identifier", json.dumps(packet))
            self.assertIn("drawing.png<br>", (dest / "index.html").read_text())

class SelectedCaseReviewTests(unittest.TestCase):
    def active_fixture(self, root):
        manifest = fixture(root)
        manifest['cases'][0]['turns'] = [{'prompt': 'Inspect the first drawing.', 'attachments': [], 'artifacts': [{'path': 'drawing.png', 'kind': 'preview', 'format': 'png'}]}]
        other = json.loads(json.dumps(manifest['cases'][0]))
        other['id'] = 'case-b'
        manifest['cases'].append(other)
        for arm in ('previous', 'candidate'):
            manifest['schedule'].append({'trial_id': 'trial-b-' + arm, 'case_id': 'case-b', 'arm': arm, 'repeat': 1})
        (root / 'manifest.json').write_text(json.dumps(manifest))
        append_event(root, {'type': 'run_started'})
        append_event(root, {'type': 'turn_started', 'trial_id': 'trial-b-candidate', 'turn': 1})
        return manifest

    def test_sealed_selected_case_can_export_while_other_cases_are_active(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            manifest = self.active_fixture(root)
            with mock.patch('skill_bench.experiment.load_experiment', return_value=manifest):
                with self.assertRaisesRegex(ValueError, 'closed'):
                    review.export_review(root, Path(directory) / 'full', seed=19)
                accepted = None
                try:
                    accepted = review.export_review(root, Path(directory) / 'selected', seed=19, selected_cases=['case-a'])
                except (TypeError, ValueError):
                    pass
            self.assertTrue(accepted is not None, 'A completed sealed selected case must be reviewable while unselected cases are active')
            self.assertEqual({entry['case_id'] for entry in accepted['entries']}, {'case-a'})
            self.assertEqual(accepted['case_selection']['case_ids'], ['case-a'])

    def test_unknown_empty_duplicate_active_and_unsealed_selections_fail_closed(self):
        for selected in ([], ['unknown'], ['case-a', 'case-a'], ['case-b'], 'case-a'):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'run'
                root.mkdir()
                manifest = self.active_fixture(root)
                with mock.patch('skill_bench.experiment.load_experiment', return_value=manifest), self.assertRaises(ValueError):
                    review.export_review(root, Path(directory) / 'packet', seed=19, selected_cases=selected)
                self.assertFalse((Path(directory) / 'packet').exists())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            manifest = self.active_fixture(root)
            (root / 'trials/trial-candidate/result-seal.json').unlink()
            with mock.patch('skill_bench.experiment.load_experiment', return_value=manifest), self.assertRaises(ValueError):
                review.export_review(root, Path(directory) / 'packet', seed=19, selected_cases=['case-a'])

    def test_unselected_unsealed_result_and_private_reference_do_not_enter_selected_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            manifest = self.active_fixture(root)
            active = root / 'trials/trial-b-candidate'
            active.mkdir()
            (active / 'result.json').write_text('{"unsealed":"active"}')
            manifest['cases'][1].update(visibility='private', assets=[{'id': 'private-reference', 'path': 'private.png', 'visibility': 'private', 'sha256': hashlib.sha256(PNG).hexdigest()}])
            (root / 'private.png').write_bytes(PNG)
            with mock.patch('skill_bench.experiment.load_experiment', return_value=manifest):
                packet = review.export_review(root, Path(directory) / 'packet', seed=19, selected_cases=['case-a'])
            self.assertEqual(packet['privacy'], 'public-sanitized')
            self.assertEqual(packet['references'], [])
            self.assertNotIn('private-reference', json.dumps(packet))
            mapping = json.loads((root / 'reviews' / (packet['review_id'] + '.arm-map.json')).read_text())
            review.validate_packet_mapping(packet, mapping)
            changed = json.loads(json.dumps(packet))
            changed['case_selection']['case_ids'].append('case-b')
            with self.assertRaises(ValueError):
                review.validate_packet_mapping(changed, mapping)

    def finish_other_case(self, root):
        for arm in ('previous', 'candidate'):
            original = root / ('trials/trial-' + arm)
            target = root / ('trials/trial-b-' + arm)
            (target / 'turn1/artifacts').mkdir(parents=True)
            (target / 'turn1/artifacts/drawing.png').write_bytes((original / 'turn1/artifacts/drawing.png').read_bytes())
            result = json.loads((original / 'result.json').read_text())
            result['trial_id'] = 'trial-b-' + arm
            path = target / 'result.json'
            path.write_text(json.dumps(result))
            seal_result(path)

    def test_disjoint_case_packets_preserve_scores_in_final_report_and_default_identity(self):
        from skill_bench import report
        from skill_bench.store import load_results
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            manifest = self.active_fixture(root)
            bundles = []
            with mock.patch('skill_bench.experiment.load_experiment', return_value=manifest):
                for index, case_id in enumerate(('case-a', 'case-b')):
                    if index:
                        self.finish_other_case(root)
                    destination = Path(directory) / case_id
                    packet = review.export_review(root, destination, seed=19, selected_cases=[case_id])
                    document = json.loads((destination / 'ratings-template.json').read_text())
                    document['reviewer'].update(id='independent-selected-reviewer', **{'class': 'human'})
                    evidence = packet['entries'][0]['turns'][0]['status_evidence']
                    for row in document['ratings'] + document['pairs']:
                        row.update(reason='Selected-case fixture; only observable evidence is rated.', evidence=[{'path': evidence['path'], 'sha256': evidence['sha256']}])
                    document['ratings'][0]['score'] = index
                    review.freeze_review(packet, document, root / 'reviews/ratings', media_root=destination)
                    mapping = json.loads((root / 'reviews' / (packet['review_id'] + '.arm-map.json')).read_text())
                    bundles.append({'packet': packet, 'document': document, 'arm_map': mapping})
                full = review.export_review(root, Path(directory) / 'default', seed=19)
                explicit_full = review.export_review(root, Path(directory) / 'explicit-full', seed=19, selected_cases=['case-b', 'case-a'])
            self.assertNotIn('case_selection', full)
            self.assertEqual(full['review_id'], review.canonical_hash({'manifest': manifest, 'seed': 19, 'view': 'artifact-only'})[:24])
            self.assertNotEqual(full['review_id'], explicit_full['review_id'])
            self.assertEqual(explicit_full['case_selection']['case_ids'], ['case-a', 'case-b'])
            combined = report.build_report(manifest, load_results(root), bundles)
            self.assertEqual(len(combined['ratings']), 4)
            self.assertEqual({row['review_id'] for row in combined['ratings']}, {bundle['packet']['review_id'] for bundle in bundles})
            self.assertEqual([row['score'] for row in combined['ratings']], [0, 'unverifiable', 1, 'unverifiable'])

    def test_review_cli_passes_repeated_case_selection_only_to_export(self):
        from skill_bench import cli
        response = {'review_id': '0' * 24, 'entries': [], 'pairs': [], 'privacy': 'local-private'}
        with mock.patch.object(review, 'export_review', return_value=response) as export, mock.patch('builtins.print'):
            self.assertEqual(cli.main(['review', '--run', '/private/run', '--output', '/private/packet', '--case', 'case-a', '--case', 'case-b']), 0)
            self.assertEqual(export.call_args.kwargs['selected_cases'], ['case-a', 'case-b'])
            self.assertEqual(cli.main(['review', '--run', '/private/run', '--packet', '/private/packet', '--ratings', '/private/ratings.json', '--case', 'case-a']), 2)


class VersionedTextReviewTests(unittest.TestCase):
    def text_run(self, root):
        manifest = fixture(root)
        manifest['cases'][0]['turns'] = [{'prompt': 'Explain the visible contour.', 'attachments': [], 'artifacts': [{'path': 'drawing.png', 'kind': 'preview', 'format': 'png'}, {'path': 'analysis.md', 'kind': 'notes', 'format': 'md'}]}]
        (root / 'manifest.json').write_text(json.dumps(manifest))
        for path in root.glob('trials/*/result.json'):
            result = json.loads(path.read_text())
            note_path = path.parent / 'turn1/artifacts/analysis.md'
            note_path.write_text('# Analysis\nThe contour maintains a shared left alignment.\n', encoding='utf-8')
            data = note_path.read_bytes()
            result['turns'][0]['artifacts'].append({'path': 'analysis.md', 'snapshot': 'turn1/artifacts/analysis.md', 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)})
            path.write_text(json.dumps(result))
            seal_result(path)
        return manifest

    def test_v2_declared_notes_are_first_class_hash_linked_evidence_and_legacy_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            manifest = self.text_run(root)
            with mock.patch('skill_bench.experiment.load_experiment', return_value=manifest):
                packet = review.export_review(root, Path(directory) / 'v2', seed=17, view='notes-process-v2')
                legacy = review.export_review(root, Path(directory) / 'legacy', seed=17, view='notes-process')
            note = packet['entries'][0]['turns'][0]['notes'][0]
            self.assertEqual(packet['notes_scope_version'], 2)
            self.assertEqual((Path(directory) / 'v2' / note['path']).read_bytes(), note['text'].encode())
            self.assertEqual((Path(directory) / 'v2' / note['path']).stat().st_mode & 0o777, 0o600)
            self.assertNotIn('notes_scope_version', legacy)
            self.assertNotIn('path', legacy['entries'][0]['turns'][0]['notes'][0])
            self.assertFalse((Path(directory) / 'legacy/text').exists())
            document = json.loads((Path(directory) / 'v2/ratings-template.json').read_text())
            document['reviewer'].update(id='independent-text-reader', **{'class': 'human'})
            for row in document['ratings'] + document['pairs']:
                row.update(reason='The declared analysis is the observed task deliverable.', evidence=[{'path': note['path'], 'sha256': note['sha256']}])
            accepted = False
            try:
                accepted = review.validate_review(packet, document, media_root=Path(directory) / 'v2')['valid']
            except ValueError:
                pass
            self.assertTrue(accepted, 'A declared text path and hash must be accepted as independent review evidence')
            html_page = (Path(directory) / 'v2/index.html').read_text()
            self.assertIn('Declared text output / process explanation', html_page)
            self.assertIn('...(turn.notes||[])', html_page)
            (Path(directory) / 'v2' / note['path']).write_text('altered text')
            with self.assertRaisesRegex(ValueError, 'hash|size'):
                review.validate_review(packet, document, media_root=Path(directory) / 'v2')

    def test_text_evidence_rejects_changed_inline_hash_credentials_unsafe_paths_and_oversize(self):
        text = '# Analysis\nAn observed contour relation.\n'
        note = {'name': 'analysis.md', 'kind': 'notes', 'format': 'md', 'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'source': 'frozen-case-declared-notes'}
        for failure in ('hash', 'secret', 'path', 'oversize'):
            with self.subTest(failure=failure):
                changed = dict(note)
                if failure == 'hash':
                    changed['text'] += 'altered'
                if failure == 'secret':
                    changed['text'] = 'api_key = PRIVATE'
                    changed['sha256'] = hashlib.sha256(changed['text'].encode()).hexdigest()
                if failure == 'path':
                    changed.update(path='text/../analysis.txt', size=len(text.encode()))
                if failure == 'oversize':
                    changed['text'] = 'x' * (review.MAX_NOTE_BYTES + 1)
                    changed['sha256'] = hashlib.sha256(changed['text'].encode()).hexdigest()
                with self.assertRaises(ValueError):
                    review.validate_declared_note(changed)

    def test_review_cli_explicit_package_ceiling_is_bounded_and_default_stays_64_mib(self):
        from skill_bench import cli
        response = {'review_id': '0' * 24, 'entries': [], 'pairs': [], 'privacy': 'local-private'}
        for argument, expected in ([], 64 * 1024 * 1024), (['--max-package-mib', '256'], 256 * 1024 * 1024):
            with mock.patch.object(review, 'export_review', return_value=response) as export, mock.patch('builtins.print'):
                self.assertEqual(cli.main(['review', '--run', '/private/run', '--output', '/private/new-packet', '--view', 'notes-process-v2', *argument]), 0)
                self.assertEqual(export.call_args.kwargs['max_total_bytes'], expected)
        for value in ('0', '257'):
            with mock.patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit):
                cli.parser().parse_args(['review', '--max-package-mib', value])

    def test_v2_reproduction_commands_redact_local_paths_and_retain_raw_source_identity(self):
        text = 'Observed alignment is still uneven.\nReproduce: /usr/bin/python3 /home/example-user/.local/state/maintainall/art-creation-ab/runtime/cairo/renderer.py --input "/home/example-user/My Work/12345678-1234-4234-8234-123456789abc/study.svg"\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            root.mkdir()
            manifest = self.text_run(root)
            for path in root.glob('trials/*/result.json'):
                result = json.loads(path.read_text())
                note = result['turns'][0]['artifacts'][-1]
                (path.parent / note['snapshot']).write_text(text)
                note.update(sha256=hashlib.sha256(text.encode()).hexdigest(), size=len(text.encode()))
                path.write_text(json.dumps(result))
                seal_result(path)
            packet = None
            with mock.patch('skill_bench.experiment.load_experiment', return_value=manifest):
                try:
                    packet = review.export_review(root, Path(directory) / 'v2', seed=21, view='notes-process-v2')
                except ValueError:
                    pass
            self.assertTrue(packet is not None, 'Legitimate configured-renderer reproduction paths must not block sanitized v2 text review')
            note = packet['entries'][0]['turns'][0]['notes'][0]
            self.assertEqual(note['source_sha256'], hashlib.sha256(text.encode()).hexdigest())
            self.assertNotEqual(note['sha256'], note['source_sha256'])
            self.assertEqual(note['transformation'], {'id': 'local-path-redaction-v1', 'changed': True})
            self.assertIn('Observed alignment is still uneven.', note['text'])
            self.assertIn('/usr/bin/python3', note['text'])
            self.assertNotIn('/home/', note['text'])
            self.assertNotIn('12345678', note['text'])
            self.assertEqual((Path(directory) / 'v2' / note['path']).read_text(), note['text'])

    def test_v2_path_transport_never_masks_credentials_identifiers_or_arm_claims(self):
        prefix = 'Reproduce with /home/private/renderer.py.\n'
        for text in ('api_key = SECRET', '{"api_key":"SECRET"}', 'Authorization: Bearer SECRET', 'Bearer SECRET', 'session 12345678-1234-4234-8234-123456789abc', 'baseline: previous', 'candidate wins'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                review.sanitize_v2_note(prefix + text, ['previous', 'candidate'])
        safe, transformation = review.sanitize_v2_note('The spacing is uneven; refine it.', ['previous', 'candidate'])
        self.assertEqual(safe, 'The spacing is uneven; refine it.')
        self.assertEqual(transformation, {'id': 'local-path-redaction-v1', 'changed': False})
        with self.assertRaises(ValueError):
            review._safe_text('/home/private/renderer.py', [])


if __name__ == "__main__":
    unittest.main()
