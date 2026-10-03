"""Hermetic tests for harden_daemon_config.py.

Every test runs against a synthetic PASEO_HOME in a temp directory; no real
daemon config is touched.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
HARDEN_PY = REPO_DIR / "harden_daemon_config.py"


def run_cli(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HARDEN_PY), "--home", str(home), *args],
        capture_output=True,
        text=True,
    )


def seed_config(home: Path, config: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps(config), encoding="utf-8")


class GetListenTest(unittest.TestCase):
    def test_missing_config_prints_empty(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            proc = run_cli(Path(raw), "get-listen")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.strip(), "")

    def test_reads_persisted_listen(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            seed_config(home, {"daemon": {"listen": "127.0.0.1:6801"}})
            proc = run_cli(home, "get-listen")
            self.assertEqual(proc.stdout.strip(), "127.0.0.1:6801")


class SetListenTest(unittest.TestCase):
    def test_writes_loopback_listen(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            proc = run_cli(home, "set-listen", "127.0.0.1:6802")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            stored = json.loads((home / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["daemon"]["listen"], "127.0.0.1:6802")

    def test_preserves_unrelated_keys(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            seed_config(
                home,
                {
                    "version": 1,
                    "daemon": {"listen": "127.0.0.1:6767", "cors": {"allowedOrigins": ["https://app.paseo.sh"]}},
                    "agents": {"providers": {"kimi": {"enabled": True}}},
                },
            )
            proc = run_cli(home, "set-listen", "127.0.0.1:6803")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            stored = json.loads((home / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["daemon"]["listen"], "127.0.0.1:6803")
            self.assertEqual(stored["daemon"]["cors"]["allowedOrigins"], ["https://app.paseo.sh"])
            self.assertEqual(stored["agents"]["providers"]["kimi"]["enabled"], True)

    def test_refuses_non_loopback_targets(self) -> None:
        for target in ("0.0.0.0:6767", "192.168.31.143:6767", "10.0.0.1:6767", ":6767"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as raw:
                home = Path(raw)
                proc = run_cli(home, "set-listen", target)
                self.assertEqual(proc.returncode, 1, target)
                self.assertFalse((home / "config.json").exists())

    def test_reports_non_loopback_previous_value(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            seed_config(home, {"daemon": {"listen": "0.0.0.0:6767"}})
            proc = run_cli(home, "set-listen", "127.0.0.1:6767")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            summary = json.loads(proc.stdout)
            self.assertEqual(summary["previous"], "0.0.0.0:6767")
            self.assertFalse(summary["previous_loopback"])
            self.assertEqual(summary["listen"], "127.0.0.1:6767")
            stored = json.loads((home / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["daemon"]["listen"], "127.0.0.1:6767")

    def test_accepts_localhost_and_ipv6_loopback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            self.assertEqual(run_cli(home, "set-listen", "localhost:6810").returncode, 0)
            stored = json.loads((home / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["daemon"]["listen"], "localhost:6810")
            self.assertEqual(run_cli(home, "set-listen", "[::1]:6811").returncode, 0)
            stored = json.loads((home / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["daemon"]["listen"], "[::1]:6811")

    def test_rejects_malformed_and_out_of_range_ports(self) -> None:
        for target in ("127.0.0.1:0", "127.0.0.1:65536", "127.0.0.1:http", "127.0.0.1"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as raw:
                proc = run_cli(Path(raw), "set-listen", target)
                self.assertEqual(proc.returncode, 1, target)

    def test_written_file_is_private(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            self.assertEqual(run_cli(home, "set-listen", "127.0.0.1:6812").returncode, 0)
            mode = (home / "config.json").stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)


class SetPasswordHashTest(unittest.TestCase):
    DUMMY_HASH = "$2b$12$" + "a" * 53

    def test_stores_hash_without_touching_listen(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            seed_config(home, {"daemon": {"listen": "127.0.0.1:6804"}})
            proc = run_cli(home, "set-password-hash", self.DUMMY_HASH)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            stored = json.loads((home / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["daemon"]["auth"]["password"], self.DUMMY_HASH)
            self.assertEqual(stored["daemon"]["listen"], "127.0.0.1:6804")

    def test_creates_auth_section_from_scratch(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            proc = run_cli(home, "set-password-hash", self.DUMMY_HASH)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            stored = json.loads((home / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["daemon"]["auth"]["password"], self.DUMMY_HASH)

    def test_rejects_plaintext_and_foreign_hashes(self) -> None:
        for value in ("hunter2", "$2b$12$short", "not-a-hash"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as raw:
                proc = run_cli(Path(raw), "set-password-hash", value)
                self.assertEqual(proc.returncode, 1, value)

    def test_rejects_corrupt_config(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            home.mkdir(parents=True, exist_ok=True)
            (home / "config.json").write_text("{ not json", encoding="utf-8")
            self.assertEqual(run_cli(home, "set-listen", "127.0.0.1:6805").returncode, 1)
            self.assertEqual(run_cli(home, "get-listen").returncode, 1)


class RemoveCorsOriginTest(unittest.TestCase):
    def test_removes_only_the_target_origin(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            seed_config(
                home,
                {"daemon": {"cors": {"allowedOrigins": ["https://app.paseo.sh", "https://ui.example.com"]}}},
            )
            proc = run_cli(home, "remove-cors-origin", "https://app.paseo.sh")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            summary = json.loads(proc.stdout)
            self.assertTrue(summary["removed"])
            self.assertEqual(summary["remaining"], ["https://ui.example.com"])
            stored = json.loads((home / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["daemon"]["cors"]["allowedOrigins"], ["https://ui.example.com"])

    def test_idempotent_when_origin_absent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            seed_config(home, {"daemon": {"cors": {"allowedOrigins": ["https://ui.example.com"]}}})
            proc = run_cli(home, "remove-cors-origin", "https://app.paseo.sh")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(json.loads(proc.stdout)["removed"])

    def test_empty_list_is_kept_as_explicit_deny(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            seed_config(home, {"daemon": {"cors": {"allowedOrigins": ["https://app.paseo.sh"]}}})
            self.assertEqual(run_cli(home, "remove-cors-origin", "https://app.paseo.sh").returncode, 0)
            stored = json.loads((home / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["daemon"]["cors"]["allowedOrigins"], [])
            # And the policy stays stable on a second run (no key resurrection).
            self.assertEqual(run_cli(home, "remove-cors-origin", "https://app.paseo.sh").returncode, 0)
            stored = json.loads((home / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["daemon"]["cors"]["allowedOrigins"], [])

    def test_missing_cors_section_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            seed_config(home, {"daemon": {"listen": "127.0.0.1:6767"}})
            proc = run_cli(home, "remove-cors-origin", "https://app.paseo.sh")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(json.loads(proc.stdout)["removed"])
            stored = json.loads((home / "config.json").read_text(encoding="utf-8"))
            self.assertNotIn("cors", stored["daemon"])


if __name__ == "__main__":
    unittest.main()
