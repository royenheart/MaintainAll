"""Offline behavior tests; these are not model-performance evaluations."""
import copy
from datetime import date
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/model-policy/scripts/resolve.py"
spec = importlib.util.spec_from_file_location("model_policy", SCRIPT)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class ModelPolicyTests(unittest.TestCase):
    """Exercise policy contracts and filesystem packaging without provider access."""

    def setUp(self):
        """Load a fresh registry and a deterministic current date for each test."""
        self.data = policy.load_registry()
        self.today = date(2026, 9, 24)

    def resolve(self, model="gpt-6-sol", variant="medium", skill="systematic-debugging", **kw):
        """Run real policy logic with a controlled wall clock, separate from replay."""
        with patch.object(policy, "date", wraps=date) as clock:
            clock.today.return_value = self.today
            return policy.resolve(self.data, model, variant, skill, **kw)

    def test_historical_replay_cannot_supply_execution_guidance(self):
        """An old snapshot remains inspectable but cannot revive expired guidance."""
        self.today = date(2026, 11, 10)
        current = self.resolve(variant="high")
        self.assertEqual(current["status"], "stale_evidence")
        self.assertEqual(current["tier"], "U")
        replay = self.resolve(variant="high", as_of=date(2026, 9, 24))
        self.assertTrue(replay["replay"])
        self.assertEqual(replay["evaluated_at"], "2026-11-10")
        self.assertEqual(replay["as_of"], "2026-09-24")
        self.assertEqual(replay["tier"], "T3")
        self.assertEqual(replay["next_action"], "replay_only_not_for_execution")
        self.assertEqual(replay["instructions"], [])
        self.assertEqual(replay["supplements"], {})
        self.assertEqual(replay["additional_skills"], [])

    def test_future_date_is_also_non_executable_replay(self):
        """A hypothetical future date cannot produce active execution guidance."""
        result = self.resolve(as_of=date(2026, 9, 25))
        self.assertTrue(result["replay"])
        self.assertEqual(result["next_action"], "replay_only_not_for_execution")
        self.assertEqual(result["instructions"], [])

    def test_current_date_keeps_normal_guidance(self):
        """Implicit and explicit current-date lookups have the same active result."""
        result = self.resolve()
        self.assertEqual(result, self.resolve(as_of=self.today))
        self.assertFalse(result["replay"])
        self.assertTrue(result["instructions"])
        self.assertEqual(result["next_action"], "proceed_with_checks")

    def test_effort_and_task_are_separate_axes(self):
        """Reasoning configuration and task domain independently affect candidate tiers."""
        self.assertEqual(self.resolve(variant="low")["tier"], "T1")
        self.assertEqual(self.resolve(variant="medium")["tier"], "T2")
        self.assertEqual(self.resolve(variant="high")["tier"], "T3")
        self.assertEqual(self.resolve(variant="high", task="tool_use")["tier"], "T2")

    def test_unknown_model_or_effort_is_not_guessed(self):
        """Missing or unmatched identities remain unassessed without model switching."""
        for model, variant in [(None, None), ("made-up", "high"),
                               ("gpt-6-sol", None), ("gpt-6-sol", "ultra"),
                               ("Qwen/Qwen3-8B", "high"), ("deepseek-v4-flash", "max")]:
            with self.subTest(model=model, variant=variant):
                result = self.resolve(model, variant)
                self.assertEqual(result["tier"], "U")
                self.assertEqual(result["profile"], "scaffolded")
                self.assertFalse(result["automatic_model_switch"])

    def test_stale_and_future_evidence_falls_back(self):
        """Expired or future review dates force the unknown tier."""
        for field, value in [("reviewed_at", "2026-07-01"), ("reviewed_at", "2027-01-01")]:
            self.data["models"]["gpt-6-sol"]["variants"]["medium"][field] = value
            self.assertEqual(self.resolve()["tier"], "U")

    def test_stale_source_falls_back_even_if_row_is_fresh(self):
        """A recent row review cannot hide an expired supporting source."""
        self.data["sources"]["openai-sol"]["accessed_at"] = "2026-06-01"
        self.assertEqual(self.resolve()["status"], "stale_evidence")

    def test_provisional_has_extra_contract_checks(self):
        """Provisional guidance includes checks and remains explicitly uncalibrated."""
        result = self.resolve()
        self.assertEqual(result["status"], "provisional")
        self.assertIn("contract-check", result["supplements"])
        self.assertTrue(result["needs_calibration"])

    def test_unassessed_cannot_claim_a_strong_tier(self):
        """Unassessed records cannot advertise assessed task tiers."""
        self.data["models"]["gpt-6-sol"]["variants"]["medium"]["status"] = "unassessed"
        with self.assertRaisesRegex(ValueError, "unassessed records must use U"):
            self.resolve()

    def test_old_or_future_observation_cannot_be_refreshed_by_opening_source(self):
        """Source access dates cannot rehabilitate stale or future observations."""
        for value in ("2026-01-01", "2027-01-01"):
            self.data["observations"][0]["observed_at"] = value
            result = self.resolve("gpt-5.4", "xhigh")
            self.assertEqual(result["tier"], "U")

    def test_known_measurement_date_also_expires(self):
        """A known measurement date bounds the useful lifetime of its evidence."""
        self.data["observations"][0]["measured_at"] = "2026-01-01"
        self.assertEqual(self.resolve("gpt-5.4", "xhigh")["status"], "stale_evidence")

    def test_small_non_thinking_model_exceeds_plugin_requirement(self):
        """A tier below the skill requirement requests decomposition or escalation."""
        result = self.resolve("Qwen/Qwen3-8B", "non-thinking", "dsh-plugin-development")
        self.assertTrue(result["capability_gap"])
        self.assertEqual(result["next_action"], "decompose_or_request_supported_escalation")

    def test_risk_checks_apply_even_to_high_candidate_tier(self):
        """High-risk review supplements apply regardless of candidate capability."""
        result = self.resolve(variant="high", risk="high")
        self.assertIn("risk-review", result["supplements"])

    def test_no_self_dependency_and_no_input_mutation(self):
        """Lookup avoids self-loading and preserves its registry input."""
        before = copy.deepcopy(self.data)
        result = self.resolve(skill="verification-before-completion")
        self.assertNotIn("verification-before-completion", result["additional_skills"])
        self.assertEqual(self.data, before)

    def test_invalid_task_skill_and_risk_rejected(self):
        """Unknown request dimensions fail explicitly instead of silently defaulting."""
        for kw in [{"task": "typo"}, {"skill": "typo"}, {"risk": "typo"}]:
            with self.assertRaises(ValueError):
                self.resolve(**kw)

    def test_invalid_evidence_tier_and_calibration_rejected(self):
        """Unsupported evidence, tier values and calibration claims are rejected."""
        for key, value in [("status", "calibrated"), ("evidence", ["invented-source"]),
                           ("task_tiers", {"coding": "T9"})]:
            data = copy.deepcopy(self.data)
            data["models"]["gpt-6-sol"]["variants"]["medium"][key] = value
            with self.assertRaises(ValueError):
                policy.validate(data)

    def test_duplicate_json_keys_rejected(self):
        """Ambiguous JSON keys fail before a registry can be consumed."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                policy.load_registry(path)

    def test_cli_is_independent_of_working_directory(self):
        """An absolute helper path resolves its bundled index from another directory."""
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(SCRIPT), "--skill", "writing-skills",
                                     "--as-of", "2026-09-24"], cwd=tmp,
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["tier"], "U")

    def test_all_development_skills_are_indexed_and_links_exist(self):
        """The policy covers shipped development skills and their resource links."""
        import re
        folders = {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}
        self.assertEqual(folders - {"model-policy"}, set(self.data["skills"]))
        for name in folders:
            path = ROOT / "skills" / name / "SKILL.md"
            text = path.read_text()
            self.assertTrue(text.startswith(f"---\nname: {name}\ndescription: "))
            self.assertIn("Shared model index is provided by the model-policy skill.", text)
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if not target.startswith(("https://", "http://", "#")):
                    self.assertTrue((path.parent / target).exists(), target)

    def bundle(self, root):
        """Copy the minimum complete adaptation bundle into a temporary skills root."""
        for name in ("model-policy", "systematic-debugging", "writing-plans",
                     "verification-before-completion"):
            shutil.copytree(ROOT / "skills" / name, root / name,
                            ignore=shutil.ignore_patterns("__pycache__"))

    def test_relocated_renamed_bundle_and_script_work_from_another_cwd(self):
        """Catalog names survive renamed directories and a relocated helper invocation."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "installed"
            self.bundle(root)
            for i, path in enumerate(sorted(root.iterdir())):
                path.rename(root / f"skill-id-{i}")
            result = policy.check_install(root)
            script = Path(result["policy_skill"]).parent / "scripts/resolve.py"
            self.assertIn("systematic-debugging", result["development_skills"])
            run = subprocess.run([sys.executable, str(script), "--model", "gpt-6-sol",
                                  "--variant", "medium", "--skill", "systematic-debugging",
                                  "--as-of", "2026-09-24"], cwd=tmp, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["tier"], "T2")

    def test_missing_companion_or_index_or_support_is_reported(self):
        """Incomplete bundles fail with an actionable missing-dependency diagnostic."""
        for missing in ("model-policy", "model-policy/registry.json", "writing-plans"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.bundle(root)
                path = root / missing
                shutil.rmtree(path) if path.is_dir() else path.unlink()
                with self.assertRaisesRegex(ValueError, "missing"):
                    policy.check_install(root)

    def test_duplicate_named_policy_is_rejected(self):
        """Duplicate catalog identities cannot silently select an arbitrary policy."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.bundle(root)
            shutil.copytree(root / "model-policy", root / "another-policy")
            with self.assertRaisesRegex(ValueError, "ambiguous skill name"):
                policy.check_install(root)

    def test_symlinked_installation_uses_real_resource_location(self):
        """Symlinked installations resolve resources beside the real policy skill."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"
            self.bundle(root)
            installed = Path(tmp) / "installed"
            installed.mkdir()
            for path in root.iterdir():
                (installed / path.name).symlink_to(path, target_is_directory=True)
            result = policy.check_install(installed)
            self.assertEqual(Path(result["registry"]), root / "model-policy/registry.json")


if __name__ == "__main__":
    unittest.main()
