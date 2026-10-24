"""Exercise real manifest, filesystem, ZIP and read-only HTTP boundaries."""
import base64
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/change-review-preview/scripts/review.py"
spec = importlib.util.spec_from_file_location("review_preview", SCRIPT)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)
RAW = b'{"counter":9007199254740993,"timeDeltas":[1,-4,2]}\n'


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case = self.root / "scope"
        (self.case / "data").mkdir(parents=True)
        (self.case / "evidence").mkdir()
        self.body = "# A measured problem\n\n![State](evidence/state.png)\n\n| Work | Before | After |\n|---|---:|---:|\n| Calls | 2 | 1 |\n\n````python\nprint('```')\n````\n\n<script>window.injected = true</script>\n"
        (self.case / "issue.md").write_text(self.body)
        (self.case / "pr.md").write_text("# Change\n\nThe same measured result.\n")
        (self.case / "change.patch").write_text("diff --git a/example.py b/example.py\n--- a/example.py\n+++ b/example.py\n@@ -1 +1 @@\n-old\n+new\n")
        (self.case / "data/raw.json").write_bytes(RAW)
        (self.case / "evidence/state.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aY1UAAAAASUVORK5CYII="))
        (self.case / "private.txt").write_text("PRIVATE_SENTINEL")
        self.value = {"project": "Review fixture", "items": [{"id": "scope", "title": "Scope reset", "root": "scope", "issue": {"title": "Repeated calls", "body": "issue.md"}, "pr": {"title": "Reset the scope", "body": "pr.md", "draft": False}, "patch": "change.patch", "files": [{"path": name, "role": role, "sha256": hashlib.sha256((self.case / name).read_bytes()).hexdigest()} for name, role in [("data/raw.json", "data"), ("evidence/state.png", "screenshot")]], "metrics": [{"label": "Counter", "before": 9007199254740993, "after": "9007199254740992", "unit": "instructions", "scope": "One recorded process window", "source": "data/raw.json"}]}]}
        self.manifest = self.root / "review.json"
        self.write()

    def write(self):
        self.manifest.write_text(json.dumps(self.value))

    def server(self):
        server = review.make_server(self.manifest, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown()
            server.server_close()
            thread.join()
        self.addCleanup(close)
        return f"http://127.0.0.1:{server.server_port}"

    def test_large_numbers_are_strings_only_in_presentation(self):
        value = review.Review(self.manifest).public()
        self.assertEqual(value["items"][0]["metrics"][0]["before"], "9007199254740993")
        self.assertNotIn("root", value["items"][0])
        self.assertEqual((self.case / "data/raw.json").read_bytes(), RAW)

    def test_archive_contains_complete_exact_files_and_hashes_only(self):
        output = self.root / "package.zip"
        index = review.pack(review.Review(self.manifest), "scope", output)
        with zipfile.ZipFile(output) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read("scope/data/raw.json"), RAW)
            self.assertEqual(archive.read("scope/issue.md").decode(), self.body)
            self.assertNotIn("scope/private.txt", archive.namelist())
            self.assertEqual(len(archive.namelist()), 6)
            self.assertEqual(index["files"]["data/raw.json"]["sha256"], hashlib.sha256(RAW).hexdigest())
            self.assertEqual(index["metrics"][0]["scope"], "One recorded process window")
            self.assertEqual(index["metrics"][0]["before"], "9007199254740993")
            self.assertEqual(json.loads(archive.read("scope/review-manifest.json")), index)

    def test_package_refuses_overwrite_and_removes_owned_partial_output(self):
        output = self.root / "existing.zip"
        output.write_bytes(b"KEEP")
        with self.assertRaises(FileExistsError):
            review.pack(review.Review(self.manifest), "scope", output)
        self.assertEqual(output.read_bytes(), b"KEEP")
        current = review.Review(self.manifest, verify=False)
        (self.case / "data/raw.json").write_bytes(b"changed")
        output = self.root / "partial.zip"
        with self.assertRaisesRegex(review.ReviewError, "changed"):
            review.pack(current, "scope", output)
        self.assertFalse(output.exists())

    def test_tampered_hash_duplicate_paths_and_missing_metric_sources_fail(self):
        (self.case / "data/raw.json").write_bytes(b"changed")
        with self.assertRaisesRegex(review.ReviewError, "SHA-256 mismatch"):
            review.Review(self.manifest)
        (self.case / "data/raw.json").write_bytes(RAW)
        item = self.value["items"][0]
        item["files"].append(dict(item["files"][0]))
        self.write()
        with self.assertRaisesRegex(review.ReviewError, "duplicate/reserved"):
            review.Review(self.manifest)
        item["files"].pop()
        item["metrics"][0]["source"] = "private.txt"
        self.write()
        with self.assertRaisesRegex(review.ReviewError, "metric source"):
            review.Review(self.manifest)

    def test_parent_absolute_and_symlink_escape_fail(self):
        for root in ["../outside", str(self.root)]:
            with self.subTest(root=root):
                self.value["items"][0]["root"] = root
                self.write()
                with self.assertRaises(review.ReviewError):
                    review.Review(self.manifest)
        self.value["items"][0]["root"] = "scope"
        outside = self.root / "outside.txt"
        outside.write_text("OUTSIDE")
        (self.case / "escape.txt").symlink_to(outside)
        self.value["items"][0]["files"].append({"path": "escape.txt", "sha256": hashlib.sha256(b"OUTSIDE").hexdigest()})
        self.write()
        with self.assertRaisesRegex(review.ReviewError, "escapes root"):
            review.Review(self.manifest)

    def test_duplicate_json_keys_and_ids_fail(self):
        self.manifest.write_text('{"project":"a","project":"b","items":[]}')
        with self.assertRaisesRegex(review.ReviewError, "Duplicate JSON key"):
            review.Review(self.manifest)
        self.value["items"].append(dict(self.value["items"][0]))
        self.write()
        with self.assertRaisesRegex(review.ReviewError, "Duplicate item"):
            review.Review(self.manifest)

    def test_http_serves_only_listed_bytes_and_has_no_write_endpoint(self):
        origin = self.server()
        query = urllib.parse.urlencode({"item": "scope", "path": "data/raw.json"})
        with urllib.request.urlopen(origin + "/file?" + query) as response:
            self.assertEqual(response.read(), RAW)
        for path in ["private.txt", "../outside.txt"]:
            with self.subTest(path=path):
                query = urllib.parse.urlencode({"item": "scope", "path": path})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(origin + "/file?" + query)
                self.assertEqual(error.exception.code, 400)
                self.assertNotIn(b"PRIVATE_SENTINEL", error.exception.read())
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(urllib.request.Request(origin + "/publish", data=b"{}"))
        self.assertEqual(error.exception.code, 405)
        with urllib.request.urlopen(origin + "/archive?item=scope") as response:
            self.assertEqual(response.headers.get_content_type(), "application/zip")
            self.assertIn("attachment", response.headers["Content-Disposition"])
            with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                self.assertEqual(archive.read("scope/data/raw.json"), RAW)
        (self.case / "data/raw.json").write_bytes(b"changed")
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(origin + "/file?item=scope&path=data/raw.json")

    def test_cli_works_from_another_directory(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "validate", "--manifest", str(self.manifest)], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["items"], 1)

    def test_http_errors_do_not_disclose_local_paths_or_manifest_values(self):
        origin = self.server()
        self.value["items"][0]["issue"]["url"] = "NOT_A_PUBLIC_URL"
        self.write()
        for failure in ("invalid manifest", "missing manifest"):
            with self.subTest(failure=failure):
                if failure == "missing manifest":
                    self.manifest.unlink()
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(origin + "/api/review")
                self.assertEqual(error.exception.code, 400)
                body = error.exception.read()
                self.assertNotIn(str(self.root).encode(), body)
                self.assertNotIn(b"NOT_A_PUBLIC_URL", body)

    def test_vendor_sources_and_licenses_are_packaged(self):
        vendor = SCRIPT.parents[1] / "assets/vendor"
        for module in json.loads((vendor / "sources.json").read_text())["modules"]:
            self.assertEqual(hashlib.sha256((vendor / module["file"]).read_bytes()).hexdigest(), module["sha256"])
            self.assertTrue((vendor / module["license"]).is_file())


if __name__ == "__main__":
    unittest.main()
