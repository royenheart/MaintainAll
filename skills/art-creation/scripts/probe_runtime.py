#!/usr/bin/env python3
"""Locate Blender or Houdini executables and optionally query Blender's version."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

COMMANDS = {"blender": ("blender",), "houdini": ("hython", "houdini")}
UNKNOWN = {"state": "unverified"}


def probe(backend: str, executable: Path | None = None, version: bool = False) -> dict:
    candidates = [str(executable.expanduser().resolve())] if executable else list(COMMANDS[backend])
    selected = None
    for name in candidates:
        found = shutil.which(name)
        if found and Path(found).is_file() and os.access(found, os.X_OK):
            selected = str(Path(found).resolve())
            break
    result = {
        "backend": backend,
        "executable": selected,
        "detection": "found" if selected else "not_found",
        "environment": dict(UNKNOWN),
        "control": dict(UNKNOWN),
        "render_display": dict(UNKNOWN),
        "export_target": dict(UNKNOWN),
        "scope": "PATH or explicit executable lookup.",
    }
    if version:
        if backend != "blender":
            result["version_check"] = {
                "state": "not_run",
                "reason": "Version queries are implemented for Blender.",
            }
        elif selected is None:
            result["version_check"] = {"state": "not_run", "reason": "Executable not found."}
        else:
            try:
                process = subprocess.run(
                    [selected, "--version"], capture_output=True, text=True, timeout=10, check=False,
                )
                result["version_check"] = {
                    "state": "ran",
                    "exit_code": process.returncode,
                    "summary": process.stdout.splitlines()[:2],
                }
            except (OSError, subprocess.TimeoutExpired) as exc:
                result["version_check"] = {"state": "failed", "reason": str(exc)}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Examples:\n"
            "  python probe_runtime.py --backend blender --json\n"
            "  python probe_runtime.py --backend blender --executable /opt/blender/blender --version\n"
            "  python probe_runtime.py --backend houdini --json\n"
            "Searches PATH or checks an explicit executable path. "
            "--version runs Blender --version with a 10-second timeout. "
            "Exit 0: probe completed (including missing executables); exit 2: invalid CLI arguments."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--backend", required=True, choices=COMMANDS, help="Selected application backend.")
    parser.add_argument("--executable", type=Path, help="Explicit executable path instead of PATH discovery.")
    parser.add_argument("--version", action="store_true", help="Query the Blender version.")
    parser.add_argument("--json", action="store_true", help="Print detection and version results as JSON.")
    args = parser.parse_args()
    result = probe(args.backend, args.executable, args.version)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['backend']}: {result['detection']}; executable={result['executable'] or 'none'}")
        print(result["scope"])
        if "version_check" in result:
            print(json.dumps(result["version_check"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
