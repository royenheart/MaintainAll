"""Requirement and evidence boundaries are observable validation contracts."""

import copy
import tempfile
import unittest
from pathlib import Path

from skill_bench.contracts import validate_case


def case():
    return {
        "schema_version": 2, "id": "example", "version": 2,
        "family": "layout", "split": "development", "assets": [],
        "turns": [{"id": "t1", "prompt": "Make the title readable.",
                   "attachments": [], "artifacts": [{"path": "a.png", "kind": "preview", "format": "png"}]},
                  {"id": "t2", "prompt": "Read date before supporting text.",
                   "attachments": [], "artifacts": [{"path": "a.png", "kind": "preview", "format": "png"}]}],
        "requirements": [{"id": "reading", "turn": 2, "quote": "Read date before supporting text."}],
        "atoms": [{"id": "reading", "dimension": "hierarchy", "criterion": "Date precedes support.",
                   "requirement_ids": ["reading"], "active_turns": [2], "depends_on": [],
                   "anchors": {"0": "Wrong", "1": "Ambiguous", "2": "Visible"},
                   "evidence": {"kind": "visual", "required_artifacts": ["a.png"]}}],
        "capabilities": ["svg"], "limits": {"turn_seconds": 600,
        "max_file_bytes": 8388608, "max_workspace_bytes": 33554432}, "provenance": {},
    }


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_rejects_requirement_not_in_prompt(self):
        value = case()
        value["requirements"][0]["quote"] = "Unrequested aesthetic priority."
        with self.assertRaisesRegex(ValueError, "requirement"):
            validate_case(value, self.root)

    def test_rejects_early_activation(self):
        value = case()
        value["atoms"][0]["active_turns"] = [1, 2]
        with self.assertRaisesRegex(ValueError, "activ"):
            validate_case(value, self.root)

    def test_rejects_dependency_cycle(self):
        value = case()
        value["atoms"][0]["depends_on"] = ["reading"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_case(value, self.root)

    def test_rejects_artifact_escape(self):
        value = case()
        value["turns"][0]["artifacts"][0]["path"] = "../outside.png"
        with self.assertRaisesRegex(ValueError, "path"):
            validate_case(value, self.root)

    def test_accepts_aligned_case_without_mutation(self):
        value = case()
        before = copy.deepcopy(value)
        self.assertEqual(validate_case(value, self.root), value)
        self.assertEqual(value, before)
