"""Check capture evidence, failure handling and source preservation without Chrome."""

import importlib.util
import json
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "skills/art-creation/scripts/capture_browser.py"
spec = importlib.util.spec_from_file_location("art_capture", SCRIPT)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source with spaces.html"
        self.source.write_text("<svg></svg>")
        self.output = self.root / "result"

    def runner(self, command, timeout):
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "Chromium test\n", "")
        target = next(x.split("=", 1)[1] for x in command if x.startswith("--screenshot="))
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 320, 240, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff" * 320 * 3) * 240)) + chunk(b"IEND", b"")
        Path(target).write_bytes(png)
        return subprocess.CompletedProcess(command, 0, "<html>rendered</html>", "")

    def test_actual_file_uri_dimensions_and_source_preservation(self):
        before = self.source.read_bytes()
        with patch.object(capture, "run_process", side_effect=self.runner):
            result = capture.capture(self.source, self.output, "/fake/chrome", 320, 240, 750, 5, [])
        self.assertTrue(result["passed"])
        self.assertEqual(result["png_dimensions"], [320, 240])
        self.assertEqual(result["command"][-1], self.source.as_uri())
        self.assertNotIn("--no-sandbox", result["command"])
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(json.loads((self.output / "capture.json").read_text())["source_sha256"], result["source_sha256"])
        self.assertEqual((self.output / "rendered.html").read_text(), "<html>rendered</html>")

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "keep"
        sentinel.write_text("keep")
        with patch.object(capture, "run_process") as runner:
            with self.assertRaises(FileExistsError):
                capture.capture(self.source, self.output, "/fake/chrome", 320, 240, 0, 5, [])
        runner.assert_not_called()
        self.assertEqual(sentinel.read_text(), "keep")

    def test_zero_exit_without_png_is_not_render_success(self):
        with patch.object(capture, "run_process", return_value=subprocess.CompletedProcess([], 0, "", "")):
            result = capture.capture(self.source, self.output, "/fake/chrome", 320, 240, 0, 5, [])
        self.assertFalse(result["passed"])
        self.assertIn("PNG", result["failure"])
        self.assertTrue((self.output / "capture.json").exists())

    def test_timeout_leaves_failure_evidence(self):
        def runner(command, timeout):
            if "--version" in command:
                return subprocess.CompletedProcess(command, 0, "test", "")
            raise subprocess.TimeoutExpired(command, timeout)
        with patch.object(capture, "run_process", side_effect=runner):
            result = capture.capture(self.source, self.output, "/fake/chrome", 320, 240, 0, 5, [])
        self.assertFalse(result["passed"])
        self.assertIn("TimeoutExpired", result["failure"])

    def test_invalid_png_is_rejected(self):
        def runner(command, timeout):
            if "--version" not in command:
                (self.output / "preview.png").write_text("not a picture")
            return subprocess.CompletedProcess(command, 0, "test", "")
        with patch.object(capture, "run_process", side_effect=runner):
            result = capture.capture(self.source, self.output, "/fake/chrome", 320, 240, 0, 5, [])
        self.assertFalse(result["passed"])

    def test_header_only_output_cannot_count_as_picture(self):
        png = self.root / "truncated.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I4sII", 13, b"IHDR", 320, 240))
        with self.assertRaises(ValueError):
            capture.png_dimensions(png)


if __name__ == "__main__":
    unittest.main()
