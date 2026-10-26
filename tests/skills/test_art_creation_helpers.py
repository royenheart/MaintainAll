"""Regression checks for resource routing and honest executable discovery."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "skills" / "art-creation"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


index = load("art_index", BUNDLE / "scripts/check_index.py")
runtime = load("art_runtime", BUNDLE / "scripts/probe_runtime.py")


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "bundle"
        shutil.copytree(BUNDLE, self.root, ignore=shutil.ignore_patterns("__pycache__"))

    def modify(self, relative, old, new):
        p = self.root / relative
        p.write_text(p.read_text().replace(old, new, 1))

    def errors(self):
        result = index.check(self.root)
        self.assertFalse(result["passed"])
        return "\n".join(e["message"] for e in result["errors"])

    def test_real_bundle_passes(self):
        self.assertTrue(index.check(self.root)["passed"])

    def test_malformed_index_header(self):
        self.modify(index.INDEX, "| ID | Read when | Resource | Type |",
                    "| ID | Read when | Location | Type |")
        self.assertIn("expected exactly one table", self.errors())

    def test_bad_routing_column_count(self):
        self.modify("SKILL.md", "| User need | Capability | Read |",
                    "| User need | Read |")
        self.assertIn("expected exactly one table", self.errors())

    def test_domain_route_structure_is_checked(self):
        self.modify("references/fashion-design.md", "| Current question | Useful representation or route |",
                    "| Current question | Destination |")
        self.assertIn("expected exactly one table", self.errors())

    def test_feedback_setup_and_streaming_routes_are_checked(self):
        for path, header in [("references/feedback-setup.md", "| Current need | Read | Verify |"), ("methods/game-engine/references/remote-preview.md", "| Option | Read | Role |")]:
            with self.subTest(path=path):
                resource = self.root / path
                original = resource.read_text()
                resource.write_text(original.replace(header, "| Invalid | Header |", 1))
                self.assertIn("expected exactly one table", self.errors())
                resource.write_text(original)

    def test_missing_resource_target(self):
        (self.root / "references/delegation.md").unlink()
        self.assertIn("missing link target", self.errors())

    def test_unindexed_resource_is_detected(self):
        (self.root / "references/added.md").write_text("# Added\n")
        self.assertIn("unindexed resource: references/added.md", self.errors())

    def test_unindexed_native_game_resource_is_detected(self):
        relative = "methods/game-engine/templates/feel-lab/added.gd"
        (self.root / relative).write_text("extends Node\n")
        self.assertIn("unindexed resource: " + relative, self.errors())

    def test_duplicate_id_and_target(self):
        p = self.root / index.INDEX
        row = next(line for line in p.read_text().splitlines() if line.startswith("| intent |"))
        p.write_text(p.read_text() + row + "\n")
        errors = self.errors()
        self.assertIn("duplicate resource ID", errors)
        self.assertIn("duplicate resource target", errors)

    def test_wrong_resource_type(self):
        self.modify(index.INDEX, "[Intent](intent-and-evidence.md) | reference",
                    "[Intent](intent-and-evidence.md) | script")
        self.assertIn("resource type does not match", self.errors())

    def test_missing_heading_anchor(self):
        self.modify("SKILL.md", "#detailed-description-and-construction-methods",
                    "#nonexistent-heading")
        self.assertIn("missing heading anchor", self.errors())

    def test_symlink_cannot_escape_bundle(self):
        p = self.root / "references/delegation.md"
        p.unlink()
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text("# Outside\n")
        p.symlink_to(outside)
        self.assertIn("escapes bundle", self.errors())

    def test_links_in_code_do_not_create_false_errors(self):
        p = self.root / "references/delegation.md"
        fence = chr(96) * 3
        p.write_text(p.read_text() + f"\n{fence}text\n[Example](missing.md)\n{fence}\n")
        self.assertTrue(index.check(self.root)["passed"])


class RuntimeTests(unittest.TestCase):
    def test_missing_backend_is_not_successful_rendering(self):
        with patch.object(runtime.shutil, "which", return_value=None):
            result = runtime.probe("blender")
        self.assertEqual(result["detection"], "not_found")
        self.assertEqual(result["render_display"]["state"], "unverified")

    def test_default_probe_never_launches_application(self):
        with patch.object(runtime.shutil, "which", return_value=None), \
                patch.object(runtime.subprocess, "run") as run:
            runtime.probe("houdini")
        run.assert_not_called()

    def test_houdini_version_option_does_not_checkout_license(self):
        with patch.object(runtime.shutil, "which", return_value=None), \
                patch.object(runtime.subprocess, "run") as run:
            result = runtime.probe("houdini", version=True)
        self.assertEqual(result["version_check"]["state"], "not_run")
        run.assert_not_called()

    def test_detected_executable_does_not_certify_environment(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "blender"
            p.write_text("#!/bin/sh\nexit 0\n")
            p.chmod(0o755)
            result = runtime.probe("blender", p)
        self.assertEqual(result["detection"], "found")
        self.assertEqual(result["environment"]["state"], "unverified")

    def test_version_timeout_is_reported_separately(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "blender"
            p.write_text("#!/bin/sh\nexit 0\n")
            p.chmod(0o755)
            with patch.object(runtime.subprocess, "run",
                              side_effect=subprocess.TimeoutExpired(["blender"], 10)):
                result = runtime.probe("blender", p, version=True)
        self.assertEqual(result["version_check"]["state"], "failed")
        self.assertEqual(result["render_display"]["state"], "unverified")


if __name__ == "__main__":
    unittest.main()
