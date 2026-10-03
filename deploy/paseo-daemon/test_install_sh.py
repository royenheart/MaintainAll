"""Hermetic tests for install.sh helpers.

The bash functions are extracted from install.sh and executed against
synthetic directory trees, so no real login shell, nvm installation, or
system toolchain is touched.
"""

from __future__ import annotations

import re
import shlex
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


class RefreshPathBodyTest(unittest.TestCase):
    """[Path] settings take the value literally: systemd does not strip
    quotes in PathModified, so a quoted path reads as non-absolute and the
    unit refuses to load. refresh_path_body must write the raw scope dir
    and reject values the literal syntax cannot carry."""

    def render(self, scope: str) -> subprocess.CompletedProcess[str]:
        script = (
            "set -euo pipefail\n"
            "die() { printf '%s\\n' \"$*\" >&2; exit 1; }\n"
            f"PKG_SCOPE_DIR={shlex.quote(scope)}\n"
            "REFRESH_SERVICE_NAME=paseo-supervisor-refresh.service\n"
            f"{extract_function('validate_path_setting')}"
            f"{extract_function('refresh_path_body')}\n"
            "refresh_path_body"
        )
        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )

    def test_path_modified_is_unquoted(self) -> None:
        scope = "/home/u/.nvm/versions/node/v24.14.0/lib/node_modules/@getpaseo"
        proc = self.render(scope)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"PathModified={scope}\n", proc.stdout)
        self.assertNotIn('PathModified="', proc.stdout)

    def test_internal_space_is_kept_literally(self) -> None:
        proc = self.render("/opt/my dir/@getpaseo")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PathModified=/opt/my dir/@getpaseo\n", proc.stdout)

    def test_unencodable_scopes_are_rejected(self) -> None:
        for scope in (
            "relative/@getpaseo",  # not absolute
            "/opt/trailing/ ",  # trailing whitespace is trimmed by systemd's parser
            '/opt/qu"ote/',  # quote
            "/opt/back\\slash/",  # backslash
            "/opt/percent%/",  # % is a unit-file specifier
        ):
            with self.subTest(scope=scope):
                self.assertNotEqual(self.render(scope).returncode, 0)


class DecidePasswordActionTest(unittest.TestCase):
    """Password flow decisions are pinned here: setting is the default, an
    unattended re-run never rotates or clears a hash silently, and the two
    env vars have a strict precedence (set wins over clear; the combination
    of both is rejected before this function runs)."""

    def decide(self, existing: int, has_env: int, has_clear: int, has_tty_flag: int) -> str:
        proc = run_function(
            "decide_password_action",
            [str(existing), str(has_env), str(has_clear), str(has_tty_flag)],
            {"PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def test_env_always_wins(self) -> None:
        for existing in (0, 1):
            for has_clear in (0, 1):
                for has_tty_flag in (0, 1):
                    with self.subTest(existing=existing, has_clear=has_clear, has_tty_flag=has_tty_flag):
                        self.assertEqual(self.decide(existing, 1, has_clear, has_tty_flag), "env")

    def test_clear_env_removes_hash(self) -> None:
        for existing in (0, 1):
            for has_tty_flag in (0, 1):
                with self.subTest(existing=existing, has_tty_flag=has_tty_flag):
                    self.assertEqual(self.decide(existing, 0, 1, has_tty_flag), "clear")

    def test_interactive_existing_offers_keep_reset_disable(self) -> None:
        self.assertEqual(self.decide(1, 0, 0, 1), "ask")

    def test_interactive_fresh_offers_set_or_none(self) -> None:
        self.assertEqual(self.decide(0, 0, 0, 1), "ask-fresh")

    def test_unattended_re_run_keeps_existing_hash(self) -> None:
        self.assertEqual(self.decide(1, 0, 0, 0), "keep")

    def test_unattended_fresh_install_generates(self) -> None:
        self.assertEqual(self.decide(0, 0, 0, 0), "generate")


class ValidatePortValueTest(unittest.TestCase):
    """--port / PASEO_PORT validation: plain integers in 1-65535 only.
    The extracted function calls die(), which the extraction would not carry
    over, so the runner defines a local stand-in first."""

    def run_validate(self, value: str) -> subprocess.CompletedProcess[str]:
        script = (
            "set -euo pipefail\n"
            "die() { printf '%s\\n' \"$*\" >&2; exit 1; }\n"
            f"{extract_function('validate_port_value')}\n"
            "validate_port_value \"$@\""
        )
        return subprocess.run(
            ["bash", "-c", script, "validate_port_value", value],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )

    def test_accepts_valid_ports(self) -> None:
        for value in ("1", "6767", "6800", "65535"):
            with self.subTest(value=value):
                proc = self.run_validate(value)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.strip(), value)

    def test_rejects_out_of_range_and_non_numeric(self) -> None:
        for value in ("0", "65536", "-1", "67.67", "abc", ""):
            with self.subTest(value=value):
                self.assertNotEqual(self.run_validate(value).returncode, 0)


if __name__ == "__main__":
    unittest.main()
