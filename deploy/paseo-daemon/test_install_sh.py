"""Hermetic tests for install.sh helpers.

The bash functions are extracted from install.sh and executed against
synthetic directory trees, so no real login shell, nvm installation, or
system toolchain is touched.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
INSTALL_SH = REPO_DIR / "install.sh"


def extract_function(name: str) -> str:
    text = INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\(\) \{{.*?\n\}}\n", text, re.MULTILINE | re.DOTALL)
    if not match:
        raise AssertionError(f"function {name} not found in install.sh")
    return match.group(0)


def run_function(name: str, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    script = f"set -euo pipefail\n{extract_function(name)}\n{name} \"$@\""
    return subprocess.run(
        ["bash", "-c", script, name, *args],
        capture_output=True,
        text=True,
        env=env,
    )


class DiscoverPaseoTest(unittest.TestCase):
    """Regression for hosts where paseo is installed under an nvm version
    that is not active (system node on PATH, or a different nvm default):
    the installer must still find the paseo shim on disk."""

    def env_with(self, path: str, home: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = {
            # /usr/bin:/bin so bash itself stays resolvable inside the child.
            "PATH": f"{path}:/usr/bin:/bin",
            "HOME": str(home),
            "NVM_DIR": str(home / ".nvm"),
            "SHELL": "/bin/bash",
        }
        if extra:
            env.update(extra)
        return env

    def make_shim(self, bin_dir: Path, name: str = "paseo") -> Path:
        bin_dir.mkdir(parents=True, exist_ok=True)
        shim = bin_dir / name
        shim.write_text("#!/bin/sh\n", encoding="utf-8")
        shim.chmod(0o755)
        return shim

    def test_prefers_paseo_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            on_path = self.make_shim(home / "on-path" / "bin")
            self.make_shim(home / ".nvm" / "versions" / "node" / "v24.0.0" / "bin")
            proc = run_function("discover_paseo", [], self.env_with(str(on_path.parent), home))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.strip(), str(on_path))

    def test_falls_back_to_newest_nvm_version(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            older = self.make_shim(home / ".nvm" / "versions" / "node" / "v20.0.0" / "bin")
            newer = self.make_shim(home / ".nvm" / "versions" / "node" / "v24.20.0" / "bin")
            self.assertNotEqual(older, newer)
            proc = run_function("discover_paseo", [], self.env_with("/usr/bin:/bin", home))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout.strip(), str(newer))

    def test_fails_when_nowhere_to_be_found(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            proc = run_function("discover_paseo", [], self.env_with("/usr/bin:/bin", home))
            self.assertNotEqual(proc.returncode, 0)


class SystemdQuoteTest(unittest.TestCase):
    """Dynamic unit arguments must stay single arguments when paths contain
    spaces, and unencodable values (CR/LF, trailing backslash) are rejected
    instead of writing a malformed unit."""

    def quote(self, value: str) -> subprocess.CompletedProcess[str]:
        return run_function("systemd_quote", [value], {"PATH": "/usr/bin:/bin"})

    def test_plain_and_space_paths_are_single_quoted_arguments(self) -> None:
        self.assertEqual(self.quote("/usr/bin/paseo").stdout.strip(), '"/usr/bin/paseo"')
        self.assertEqual(self.quote("/opt/my dir/paseo").stdout.strip(), '"/opt/my dir/paseo"')

    def test_backslash_and_quote_are_escaped(self) -> None:
        self.assertEqual(self.quote('/a"b').stdout.strip(), '"/a\\"b"')
        self.assertEqual(self.quote("/a/b").stdout.strip(), '"/a/b"')

    def test_unencodable_values_are_rejected(self) -> None:
        self.assertNotEqual(self.quote("/a/b\\").returncode, 0)  # trailing backslash
        self.assertNotEqual(self.quote("/a/b\n").returncode, 0)  # CR/LF


if __name__ == "__main__":
    unittest.main()
