"""Offline checks for reference inputs, private rubrics and blind review."""

import binascii
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zlib


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "benchmarks/art_creation_ab/complex.py"


def image(width=8, height=8):
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", binascii.crc32(name + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress((b"\0" + b"\0" * width * 3) * height)) + chunk(b"IEND", b"")


def fixture(root):
    import hashlib
    data = image()
    (root / "reference.png").write_bytes(data)
    for arm in ("old", "new"):
        (root / arm).mkdir()
        (root / arm / "SKILL.md").write_text("# Art Creation\n" + arm)
    card = {"schema_version": 1, "id": "test-case", "attachments": [{"id": "reference", "path": "reference.png", "sha256": hashlib.sha256(data).hexdigest(), "source": "Original offline fixture", "license": "CC0"}], "rounds": [{"prompt": "Create editable art and a rendered preview.", "attachments": ["reference"] if turn == 0 else [], "required_artifacts": [{"path": "art.svg", "kind": "editable", "format": "svg"}, {"path": "art.png", "kind": "preview", "format": "png", "width": 8, "height": 8}]} for turn in range(3)], "rubric": [{"id": "relation", "criterion": "SECRET_REVIEW_ONLY_RELATION", "anchors": {"0": "Missing", "1": "Partial", "2": "Clear"}}], "limits": {"timeout_seconds": 600, "per_file_bytes": 8388608, "workspace_bytes": 33554432}}
    (root / "card.json").write_text(json.dumps(card))
    return card


def module():
    spec = importlib.util.spec_from_file_location("art_complex_test", ENTRY)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def prepare_args(root, cards):
    return SimpleNamespace(output=str(root / "run"), renderer=str(module().DEFAULT_RENDERER), task_card=cards,
                           max_cli_calls=12, old_dir=str(root / "old"), new_dir=str(root / "new"),
                           old_commit=None, new_commit=None, repo=str(ROOT))


class ComplexTests(unittest.TestCase):
    def test_matching_delivery_and_agent_self_scores_leave_quality_unassessed(self):
        m = module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            card = fixture(root)
            (root / "art.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>My quality score is 2</text></svg>')
            (root / "art.png").write_bytes(image())
            (root / "notes.md").write_text("I rate myself 2 on every criterion.")
            scored = m.artifact_checks(root, card["rounds"][0])
            self.assertTrue(scored["delivery_pass"])
            self.assertEqual(scored["quality_status"], "unassessed")
            self.assertIsNone(scored["quality_scores"])
            captured = m.capture(root, root / "captured", card["limits"])
            self.assertTrue(any(item["path"] == "notes.md" and item.get("sha256") for item in captured["artifacts"]))

    def test_input_hash_and_complete_png_are_checked_before_execution(self):
        m = module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            (root / "reference.png").write_bytes(image(9, 8))
            with self.assertRaisesRegex(ValueError, "hash"):
                m.load_card(root / "card.json")
        with self.assertRaises(ValueError):
            m.png_info(b"\x89PNG\r\n\x1a\n")
        corrupt = bytearray(image())
        corrupt[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC"):
            m.png_info(bytes(corrupt))

    def test_oversized_files_are_explicitly_rejected_not_silently_dropped(self):
        m = module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "oversized.svg").write_bytes(b"x" * 1025)
            captured = m.capture(root, root / "snapshot", {"per_file_bytes": 1024, "workspace_bytes": 2048})
            self.assertFalse(captured["passed"])
            self.assertEqual(captured["artifacts"][0]["capture_status"], "rejected_due_to_workspace_violation")

    def test_commands_attach_real_images_and_resume_the_exact_uuid(self):
        m = module()
        identifier = "12345678-1234-1234-1234-123456789abc"
        with mock.patch.object(m.core, "host_skill_paths", return_value=[]):
            command = m.command("codex", Path("/runtime/codex"), Path("/workspace"), Path("/runtime/cairo"), Path("/private/final"), [Path("/workspace/inputs/one.jpg"), Path("/workspace/inputs/two.png")], identifier)
        self.assertEqual(command.count("--image"), 2)
        self.assertEqual(command[-3:], ["--", identifier, "-"])
        self.assertNotIn("--last", command)
        self.assertNotIn("--ephemeral", command)
        self.assertTrue(any('"inputs"="read"' in item for item in command))

    def test_three_round_continuation_preserves_stdout_and_does_not_repeat_first_call(self):
        m = module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            m.prepare(prepare_args(root, [str(root / "card.json")]))
            script = root / "offline-agent.py"
            script.write_text("import json,pathlib,sys,time\nsys.stdin.read()\ntime.sleep(1.1)\np=pathlib.Path('call-count');n=int(p.read_text())+1 if p.exists() else 1;p.write_text(str(n))\npathlib.Path('art.svg').write_text('<svg xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M0 0L1 1\"/></svg>')\npathlib.Path('art.png').write_bytes(" + repr(image()) + ")\nprint(json.dumps({'type':'thread.started','thread_id':'12345678-1234-1234-1234-123456789abc'}))\nprint(json.dumps({'type':'turn.completed','usage':{'input_tokens':n*100,'cached_input_tokens':n*50,'output_tokens':n*10}}))\n")
            seen = []
            def fake_command(*arguments):
                seen.append(arguments[-1])
                return [sys.executable, str(script)]
            with mock.patch.object(m.core, "doctor", return_value={"model_called": False}), mock.patch.object(m.core, "runtime", return_value=("unused", root)), mock.patch.object(m, "command", side_effect=fake_command), mock.patch.object(m, "rollout_evidence", return_value={"reference_input_image_items": 1}):
                arguments = SimpleNamespace(output=str(root / "run"), arm="old", task=None, through_turn=1)
                m.run(arguments)
                arguments.through_turn = 3
                m.run(arguments)
            self.assertEqual(seen, [None, "12345678-1234-1234-1234-123456789abc", "12345678-1234-1234-1234-123456789abc"])
            results = m.rows(root / "run")
            self.assertEqual(len(results), 3)
            self.assertEqual([row["usage"]["input_tokens"] for row in results], [100, 100, 100])
            self.assertTrue(all((root / "run/old/test-case" / ("round" + str(turn)) / "events.jsonl").stat().st_size for turn in (1, 2, 3)))

    def test_blind_comparisons_do_not_mix_arms_or_tasks_and_ratings_respect_turns(self):
        m = module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            card = fixture(root)
            card["rubric"].append({"id": "final-only", "criterion": "Final feedback only", "anchors": {"0": "Missing", "1": "Partial", "2": "Clear"}, "applicable_turns": [3]})
            (root / "card.json").write_text(json.dumps(card))
            second = {**card, "id": "second-case"}
            (root / "second.json").write_text(json.dumps(second))
            m.prepare(prepare_args(root, [str(root / "card.json"), str(root / "second.json")]))
            for arm in ("old", "new"):
                for task in ("test-case", "second-case"):
                    for turn in (1, 2, 3):
                        phase = root / "run" / arm / task / ("round" + str(turn))
                        artifacts = phase / "artifacts"
                        artifacts.mkdir(parents=True)
                        content = arm + task + (str(turn) if arm == "new" and task == "test-case" else "fixed")
                        (artifacts / "art.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>' + content + '</text></svg>')
                        (artifacts / "art.png").write_bytes(image())
                        (artifacts / "notes.md").write_text("Actual handoff")
                        result = {"arm": arm, "task": task, "turn": turn, "image_evidence": {}, "outcome": m.artifact_checks(artifacts, card["rounds"][turn - 1])}
                        m.core.dump(phase / "result.json", result)
            m.blind_export(SimpleNamespace(output=str(root / "run"), dest=str(root / "packet")))
            packet = json.loads((root / "packet/review.json").read_text())
            mapping = json.loads(next((root / "run").glob("blind-map-*.json")).read_text())
            for entry in packet["entries"]:
                if mapping[entry["id"]] == {"arm": "new", "task": "test-case"}:
                    comparisons = entry["turns"][1]["artifact_hash_comparisons"]
                    self.assertFalse(next(item["same_as_previous"] for item in comparisons if item["path"] == "art.svg"))
            ratings = json.loads((root / "packet/ratings.json").read_text())
            self.assertEqual(len(ratings["ratings"]), 16)
            self.assertTrue(all(item["turn"] == 3 for item in ratings["ratings"] if item["atom"] == "final-only"))
            self.assertNotIn('"arm"', (root / "packet/review.json").read_text())
            self.assertFalse(list((root / "packet").rglob("*map*")))

    def test_invalid_applicability_is_rejected_before_preparation(self):
        m = module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            card = fixture(root)
            card["rubric"][0]["applicable_turns"] = [4]
            (root / "card.json").write_text(json.dumps(card))
            with self.assertRaisesRegex(ValueError, "applicable"):
                m.load_card(root / "card.json")

    def test_prepare_freezes_real_inputs_without_injecting_the_rubric(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture(root)
            result = subprocess.run([sys.executable, str(ENTRY), "prepare", "--old-dir", str(root / "old"), "--new-dir", str(root / "new"), "--task-card", str(root / "card.json"), "--output", str(root / "run"), "--max-cli-calls", "6"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((root / "run/manifest.json").read_text())
            self.assertEqual(manifest["max_cli_calls"], 6)
            for arm in ("old", "new"):
                workspace = root / "run" / arm / "test-case/workspace"
                self.assertEqual((workspace / "inputs/reference.png").read_bytes(), (root / "reference.png").read_bytes())
                self.assertFalse(any("SECRET_REVIEW_ONLY" in path.read_text(errors="ignore") for path in workspace.rglob("*") if path.is_file()))
            self.assertEqual((root / "run").stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
