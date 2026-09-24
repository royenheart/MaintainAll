"""Offline behavior tests; these are not model-performance evaluations."""
import copy
from datetime import date
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/model-policy/scripts/resolve.py"
spec = importlib.util.spec_from_file_location("model_policy", SCRIPT)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class ModelPolicyTests(unittest.TestCase):
    def setUp(self):
        self.data = policy.load_registry()
        self.today = date(2026, 9, 24)

    def resolve(self, model="gpt-6-sol", variant="medium", skill="systematic-debugging", **kw):
        return policy.resolve(self.data, model, variant, skill, as_of=self.today, **kw)

    def test_effort_and_task_are_separate_axes(self):
        self.assertEqual(self.resolve(variant="low")["tier"], "T1")
        self.assertEqual(self.resolve(variant="medium")["tier"], "T2")
        self.assertEqual(self.resolve(variant="high")["tier"], "T3")
        self.assertEqual(self.resolve(variant="high", task="tool_use")["tier"], "T2")

    def test_unknown_model_or_effort_is_not_guessed(self):
        for model, variant in [(None, None), ("made-up", "high"),
                               ("gpt-6-sol", None), ("gpt-6-sol", "ultra"),
                               ("Qwen/Qwen3-8B", "high"), ("deepseek-v4-flash", "max")]:
            with self.subTest(model=model, variant=variant):
                result = self.resolve(model, variant)
                self.assertEqual(result["tier"], "U")
                self.assertEqual(result["profile"], "scaffolded")
                self.assertFalse(result["automatic_model_switch"])

    def test_stale_and_future_evidence_falls_back(self):
        for field, value in [("reviewed_at", "2026-07-01"), ("reviewed_at", "2027-01-01")]:
            self.data["models"]["gpt-6-sol"]["variants"]["medium"][field] = value
            self.assertEqual(self.resolve()["tier"], "U")

    def test_stale_source_falls_back_even_if_row_is_fresh(self):
        self.data["sources"]["openai-sol"]["accessed_at"] = "2026-06-01"
        self.assertEqual(self.resolve()["status"], "stale_evidence")

    def test_provisional_has_extra_contract_checks(self):
        result = self.resolve()
        self.assertEqual(result["status"], "provisional")
        self.assertIn("contract-check", result["supplements"])
        self.assertTrue(result["needs_calibration"])

    def test_unassessed_cannot_claim_a_strong_tier(self):
        self.data["models"]["gpt-6-sol"]["variants"]["medium"]["status"] = "unassessed"
        with self.assertRaisesRegex(ValueError, "unassessed records must use U"):
            self.resolve()

    def test_old_or_future_observation_cannot_be_refreshed_by_opening_source(self):
        for value in ("2026-01-01", "2027-01-01"):
            self.data["observations"][0]["observed_at"] = value
            result = self.resolve("gpt-5.4", "xhigh")
            self.assertEqual(result["tier"], "U")

    def test_known_measurement_date_also_expires(self):
        self.data["observations"][0]["measured_at"] = "2026-01-01"
        self.assertEqual(self.resolve("gpt-5.4", "xhigh")["status"], "stale_evidence")

    def test_small_non_thinking_model_exceeds_plugin_requirement(self):
        result = self.resolve("Qwen/Qwen3-8B", "non-thinking", "dsh-plugin-development")
        self.assertTrue(result["capability_gap"])
        self.assertEqual(result["next_action"], "decompose_or_request_supported_escalation")

    def test_risk_checks_apply_even_to_high_candidate_tier(self):
        result = self.resolve(variant="high", risk="high")
        self.assertIn("risk-review", result["supplements"])

    def test_no_self_dependency_and_no_input_mutation(self):
        before = copy.deepcopy(self.data)
        result = self.resolve(skill="verification-before-completion")
        self.assertNotIn("verification-before-completion", result["additional_skills"])
        self.assertEqual(self.data, before)

    def test_invalid_task_skill_and_risk_rejected(self):
        for kw in [{"task": "typo"}, {"skill": "typo"}, {"risk": "typo"}]:
            with self.assertRaises(ValueError):
                self.resolve(**kw)

    def test_invalid_evidence_tier_and_calibration_rejected(self):
        for key, value in [("status", "calibrated"), ("evidence", ["invented-source"]),
                           ("task_tiers", {"coding": "T9"})]:
            data = copy.deepcopy(self.data)
            data["models"]["gpt-6-sol"]["variants"]["medium"][key] = value
            with self.assertRaises(ValueError):
                policy.validate(data)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                policy.load_registry(path)

    def test_cli_is_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(SCRIPT), "--skill", "writing-skills",
                                     "--as-of", "2026-09-24"], cwd=tmp,
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["tier"], "U")

    def test_all_development_skills_are_indexed_and_links_exist(self):
        import re
        folders = {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}
        self.assertEqual(folders - {"model-policy"}, set(self.data["skills"]))
        for name in folders:
            path = ROOT / "skills" / name / "SKILL.md"
            text = path.read_text()
            self.assertTrue(text.startswith(f"---\nname: {name}\ndescription: "))
            self.assertIn("Model policy index - model-policy/registry.json.", text)
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if not target.startswith(("https://", "http://", "#")):
                    self.assertTrue((path.parent / target).exists(), target)


if __name__ == "__main__":
    unittest.main()
