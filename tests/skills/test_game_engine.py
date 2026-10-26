"""Check native project operations and real HTTP delivery without an engine install."""

from functools import partial
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "skills/art-creation/methods/game-engine/scripts/godot_project.py"
SPEC = importlib.util.spec_from_file_location("godot_project", HELPER)
godot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(godot)


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "source project"
        godot.initialize(self.project)

    def test_initialize_preserves_native_project_and_existing_work(self):
        self.assertTrue((self.project / "project.godot").is_file())
        self.assertTrue((self.project / "main.tscn").is_file())
        self.assertFalse((self.project / ".godot").exists())
        (self.project / "keep.txt").write_text("kept")
        with self.assertRaisesRegex(ValueError, "new directory"):
            godot.initialize(self.project)
        self.assertEqual((self.project / "keep.txt").read_text(), "kept")
        dangling = self.root / "existing alias"
        dangling.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(ValueError, "new directory"):
            godot.initialize(dangling)

    def test_doctor_matches_versions_with_and_without_a_patch_number(self):
        for version, folder in [("4.7.2.stable.official.example", "4.7.2.stable"), ("4.5.stable.official.example", "4.5.stable")]:
            with self.subTest(version=version), patch.object(godot, "engine_path", return_value="godot"), patch.object(godot, "run_engine", return_value=version), patch.object(godot.sys, "stdout", new_callable=io.StringIO) as output:
                self.assertEqual(godot.main(["doctor"]), 0)
                self.assertEqual(Path(json.loads(output.getvalue())["template_directory"]).name, folder)

    def test_zero_exit_script_error_is_a_failed_check(self):
        result = subprocess.CompletedProcess([], 0, "", "SCRIPT ERROR: Parse Error\n")
        with patch.object(godot.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "Parse Error"):
                godot.run_engine("godot", ["--headless"])

    def test_nested_export_is_rejected_before_execution(self):
        alias = self.root / "source alias"
        alias.symlink_to(self.project, target_is_directory=True)
        with patch.object(godot, "check") as check:
            with self.assertRaisesRegex(ValueError, "outside the source"):
                godot.export("godot", self.project, "Web", alias / "build")
            check.assert_not_called()

    def test_export_uses_engine_preset_and_records_output_hashes(self):
        target = self.root / "build with spaces"
        calls = []

        def fake_engine(engine, args, **kwargs):
            calls.append(args)
            if "--export-release" in args:
                Path(args[-1]).write_text("engine-generated loader")
                (target / "index.wasm").write_bytes(b"wasm")
                (target / "index.pck").write_bytes(b"pack")
            return "4.7.2.stable.official.example"

        with patch.object(godot, "run_engine", side_effect=fake_engine):
            result = godot.export("godot", self.project, "Web", target)
        self.assertTrue(result["exported"])
        self.assertIn(["--headless", "--path", str(self.project), "--export-release", "Web", str(target / "index.html")], calls)
        manifest = json.loads((target / "build-manifest.json").read_text())
        self.assertEqual(manifest["files"]["index.pck"], hashlib.sha256(b"pack").hexdigest())
        self.assertNotIn(str(self.root), json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "new directory"):
            godot.export("godot", self.project, "Web", target)

    def test_source_and_incomplete_tls_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Web export"):
            godot.serve(self.project, "127.0.0.1", 0)
        with self.assertRaisesRegex(ValueError, "together"):
            godot.serve(self.root, "127.0.0.1", 0, cert="example.crt")

    def test_real_http_serves_wasm_and_isolation_headers(self):
        (self.root / "index.wasm").write_bytes(b"test-wasm")
        (self.root / "empty").mkdir()

        class QuietHandler(godot.PreviewHandler):
            def log_message(self, *args):
                pass

        server = godot.ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(self.root), isolated=True))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/index.wasm", timeout=5) as response:
                self.assertEqual(response.read(), b"test-wasm")
                self.assertEqual(response.headers["Content-Type"], "application/wasm")
                self.assertEqual(response.headers["Cross-Origin-Opener-Policy"], "same-origin")
                self.assertEqual(response.headers["Cross-Origin-Embedder-Policy"], "require-corp")
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "/empty/", timeout=5)
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
