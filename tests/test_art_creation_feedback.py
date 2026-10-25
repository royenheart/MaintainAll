"""Offline checks for genuine feedback turns and artifact evidence."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("art_feedback", ROOT / "benchmarks/art_creation_ab/feedback.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FeedbackTests(unittest.TestCase):
    def test_code_mode_image_evidence_is_scoped_to_the_real_turn(self):
        identifier = "12345678-1234-1234-1234-123456789abc"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = root / "sessions/2026/10/09"
            session.mkdir(parents=True)
            events = [
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "call_id": "first", "input": "image(await tools.view_image({path: 'a.png'}));"}},
                {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "first", "output": [{"type": "input_image", "image_url": "private-image"}]}},
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "call_id": "second", "input": "image(await tools.view_image({path: 'b.png'}));"}},
                {"type": "response_item", "payload": {"type": "custom_tool_call_output", "call_id": "second", "output": "Image file not found"}},
            ]
            (session / ("rollout-" + identifier + ".jsonl")).write_text("\n".join(json.dumps(event) for event in events))
            with mock.patch.dict("os.environ", {"CODEX_HOME": str(root)}):
                first = MODULE.image_evidence(identifier, turn=1)
                second = MODULE.image_evidence(identifier, turn=2)
            self.assertEqual(first["view_image_calls_with_image_outputs"], 1)
            self.assertEqual(first["image_items_from_view_calls"], 1)
            self.assertEqual(second["view_image_calls"], 1)
            self.assertEqual(second["view_image_calls_with_image_outputs"], 0)

    def test_resumed_usage_is_a_delta_of_thread_totals(self):
        first = {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 20}
        second = {"input_tokens": 180, "cached_input_tokens": 120, "output_tokens": 35}
        result = MODULE.turn_usage(second, first)
        self.assertEqual(result["input_tokens"], 80)
        self.assertEqual(result["uncached_input_tokens"], 20)
        self.assertEqual(result["output_tokens"], 15)
        self.assertEqual(result["total_tokens"], 95)

    def test_resume_uses_the_exact_thread_and_preserves_isolation_flags(self):
        identifier = "12345678-1234-1234-1234-123456789abc"
        with mock.patch.object(MODULE.core, "host_skill_paths", return_value=[]):
            command = MODULE.command("codex", Path("/runtime/codex"), Path("/workspace"),
                                     Path("/runtime/cairo"), Path("/private/final.txt"), identifier)
        self.assertIn("resume", command)
        self.assertIn(identifier, command)
        self.assertNotIn("--last", command)
        self.assertNotIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)

    def test_source_geometry_samples_do_not_pass_on_unrelated_decoration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            one = '<svg xmlns="http://www.w3.org/2000/svg"><path id="ribbon-a" d="M0 0Q20 20 40 0"/><circle cx="1"/></svg>'
            two = one.replace('cx="1"', 'cx="2"')
            (root / "one.svg").write_text(one)
            (root / "two.svg").write_text(two)
            self.assertEqual(MODULE.source_delta(root / "one.svg", root / "two.svg", "ribbon-a"), 0)
            (root / "two.svg").write_text(two.replace('Q20 20', 'Q20 30'))
            self.assertGreater(MODULE.source_delta(root / "one.svg", root / "two.svg", "ribbon-a"), 0)


if __name__ == "__main__":
    unittest.main()
