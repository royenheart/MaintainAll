"""Offline acceptance checks for the small, private old/new skill runner."""

import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "benchmarks/art_creation_ab/run.py"
SPEC = importlib.util.spec_from_file_location("art_ab", RUNNER)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrepareTests(unittest.TestCase):
    def test_global_agents_fail_closed_before_any_sandbox_or_model_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("An isolated test instruction fixture.")
            with mock.patch.dict(MODULE.os.environ, {"CODEX_HOME": directory}), \
                    mock.patch.object(MODULE, "runtime", return_value=("unused", root)), \
                    mock.patch.object(MODULE.subprocess, "run") as sandbox:
                with self.assertRaisesRegex(ValueError, "Global Codex AGENTS"):
                    MODULE.doctor()
                sandbox.assert_not_called()

    def test_changed_runtime_is_rejected_before_any_preflight_or_model_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps({"state": "prepared", "model": "changed-model"}))
            with mock.patch.object(MODULE, "doctor") as preflight:
                with self.assertRaisesRegex(ValueError, "runtime identity"):
                    MODULE.run(type("Args", (), {"output": str(root)})())
                preflight.assert_not_called()

    def test_prepare_stages_distinct_skills_and_fixed_run_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("old", "new"):
                skill = root / name
                skill.mkdir()
                (skill / "SKILL.md").write_text(f"# Art Creation\n{name} guidance\n")
            output = root / "private-run"
            result = subprocess.run(
                [sys.executable, str(RUNNER), "prepare", "--old-dir", str(root / "old"),
                 "--new-dir", str(root / "new"), "--task", "expressive-ribbon",
                 "--output", str(output)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["model"], "gpt-6.1-sol")
            self.assertEqual(manifest["effort"], "low")
            self.assertEqual(manifest["cli_invocations"], 2)
            self.assertNotEqual(manifest["skills"]["old"]["sha256"],
                                manifest["skills"]["new"]["sha256"])
            for arm in ("old", "new"):
                skill = output / arm / "expressive-ribbon" / "workspace" / "skill" / "SKILL.md"
                self.assertEqual(skill.read_text(), f"# Art Creation\n{arm} guidance\n")
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)

    def test_prepare_rejects_a_skill_symlink_to_host_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text("# Skill\n")
            (root / "private.txt").write_text("private canary")
            (skill / "escape.txt").symlink_to(root / "private.txt")
            result = subprocess.run(
                [sys.executable, str(RUNNER), "prepare", "--old-dir", str(skill),
                 "--new-dir", str(skill), "--output", str(root / "run")],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symbolic links", result.stderr)


class EvidenceTests(unittest.TestCase):
    def test_multiple_usage_records_are_not_silently_added(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text('\n'.join(json.dumps({"type": "turn.completed", "usage": {
                "input_tokens": 100, "output_tokens": 20}}) for _ in range(2)))
            result = MODULE.usage(path)
            self.assertEqual(result["usage_status"], "ambiguous")
            self.assertIsNone(result["total_tokens"])

    def test_timeout_cleanup_stops_the_process_group(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        MODULE.stop(process)
        self.assertIsNotNone(process.poll())

    def test_valid_vectors_pass_without_inventing_a_preference_score(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in [("a", 40), ("b", 80)]:
                (root / f"preview-{name}.svg").write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 240">'
                    '<!-- An editable vector may contain harmless comments. -->'
                    f'<path fill="#58dcff" d="M10 10 Q{value} 20 30 100 Z"/></svg>'
                )
            (root / "brief.json").write_text(json.dumps({
                "intent_hypotheses": ["An airy curve may express motion."],
                "alternatives": [{"id": "a"}, {"id": "b"}],
                "confirmed_preferences": [], "pending_preferences": ["Choose a direction."],
                "capability_limits": [],
            }))
            result = subprocess.run(
                [sys.executable, str(RUNNER), "check", "--workspace", str(root),
                 "--task", "expressive-ribbon"], capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            score = json.loads(result.stdout)
            self.assertTrue(score["mechanical_pass"])
            self.assertIsNone(score["preference_score"])
            (root / "preview-b.svg").write_text('<svg><script>bad()</script></svg>')
            result = subprocess.run(
                [sys.executable, str(RUNNER), "check", "--workspace", str(root),
                 "--task", "expressive-ribbon"], capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertFalse(json.loads(result.stdout)["mechanical_pass"])

    def test_usage_keeps_cached_input_in_input_and_currency_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "events.jsonl"
            events.write_text(json.dumps({"type": "turn.completed", "usage": {
                "input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 20,
            }}) + "\n")
            result = subprocess.run(
                [sys.executable, str(RUNNER), "usage", "--events", str(events)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            usage = json.loads(result.stdout)
            self.assertEqual(usage["uncached_input_tokens"], 40)
            self.assertEqual(usage["total_tokens"], 120)
            self.assertIsNone(usage["currency_cost"])
            self.assertIsNone(usage["provider_requests"])


if __name__ == "__main__":
    unittest.main()
