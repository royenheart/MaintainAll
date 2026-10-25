#!/usr/bin/env python3
"""Capture a local HTML/SVG with an existing Chromium browser and explicit evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import struct
import subprocess
import zlib
from pathlib import Path


def run_process(command: list[str], timeout: float) -> subprocess.CompletedProcess:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               start_new_session=(os.name == "posix"))
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def png_dimensions(path: Path) -> list[int]:
    if not path.is_file():
        raise ValueError("Missing PNG output")
    dimensions = None
    has_pixels = False
    with path.open("rb") as handle:
        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Invalid PNG signature")
        while True:
            header = handle.read(8)
            if len(header) != 8:
                raise ValueError("Incomplete PNG chunks")
            length, kind = struct.unpack(">I4s", header)
            if length > path.stat().st_size - handle.tell() - 4:
                raise ValueError("Truncated PNG chunk")
            data, crc = handle.read(length), handle.read(4)
            if struct.unpack(">I", crc)[0] != zlib.crc32(kind + data):
                raise ValueError("Invalid PNG chunk checksum")
            if dimensions is None:
                if kind != b"IHDR" or length != 13:
                    raise ValueError("Missing PNG image header")
                dimensions = list(struct.unpack(">II", data[:8]))
                if not all(dimensions):
                    raise ValueError("Empty PNG dimensions")
            if kind == b"IDAT" and length:
                has_pixels = True
            if kind == b"IEND":
                if length or not has_pixels:
                    raise ValueError("Missing PNG image data")
                return dimensions


def capture(source: Path, output: Path, browser: str, width: int, height: int,
            virtual_time_ms: int, timeout: float, browser_args: list[str]) -> dict:
    source = source.expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError("Source must be a local file")
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    screenshot = output / "preview.png"
    command = [browser, "--headless", "--no-first-run", "--disable-background-networking",
               "--hide-scrollbars", "--force-device-scale-factor=1",
               f"--window-size={width},{height}", f"--user-data-dir={output / 'profile'}",
               f"--screenshot={screenshot}", "--dump-dom"]
    if virtual_time_ms:
        command.append(f"--virtual-time-budget={virtual_time_ms}")
    command.extend(browser_args)
    command.append(source.as_uri())
    result = {"passed": False, "source": str(source),
              "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "viewport_css_pixels": [width, height], "device_scale": 1,
              "virtual_time_ms": virtual_time_ms, "command": command,
              "scope": "One rendered frame and DOM; no playback, preference or target-runtime acceptance."}
    try:
        version = run_process([browser, "--version"], min(timeout, 5))
        result["browser_version"] = version.stdout.strip().splitlines()[:1]
        process = run_process(command, timeout)
        result["exit_code"] = process.returncode
        (output / "browser.log").write_text(process.stderr)
        (output / "rendered.html").write_text(process.stdout)
        if process.returncode:
            raise RuntimeError(f"Browser exited {process.returncode}; inspect browser.log")
        result["png_dimensions"] = png_dimensions(screenshot)
        result["png_sha256"] = hashlib.sha256(screenshot.read_bytes()).hexdigest()
        result["preview"] = str(screenshot)
        result["passed"] = True
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result["failure"] = f"{type(exc).__name__}: {exc}"
    (output / "capture.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Value must be positive")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  python capture_browser.py study.html --output ./capture-01 --width 800 --height 600\n"
               "  python capture_browser.py overlay.svg --browser /opt/chrome/chrome --output ./capture-02\n\n"
               "Requires an installed Chromium-compatible browser. Creates a new output directory containing "
               "preview.png, rendered.html, browser.log, capture.json and a separate browser profile. "
               "Display preview.png using the host image tool. "
               "Exit 0: PNG captured; 1: execution/capture failed; 2: invalid arguments.")
    parser.add_argument("source", type=Path, help="Actual local HTML or SVG input; referenced assets must be available.")
    parser.add_argument("--output", type=Path, required=True, help="New directory for capture artifacts.")
    parser.add_argument("--browser", help="Explicit browser executable; default: discover Chromium or Chrome on PATH.")
    parser.add_argument("--width", type=positive, default=800, help="Viewport width in CSS pixels (default: 800).")
    parser.add_argument("--height", type=positive, default=600, help="Viewport height in CSS pixels (default: 600).")
    parser.add_argument("--virtual-time-ms", type=int, default=1000, help="Browser virtual-time budget; zero disables it (default: 1000).")
    parser.add_argument("--timeout", type=positive, default=30, help="Wall-clock timeout in seconds (default: 30).")
    parser.add_argument("--browser-arg", action="append", default=[], help="Browser runtime flag; use --browser-arg=--flag.")
    args = parser.parse_args()
    if args.virtual_time_ms < 0:
        parser.error("--virtual-time-ms must be nonnegative")
    browser = shutil.which(args.browser) if args.browser else next(
        (found for name in ("chromium", "chromium-browser", "google-chrome", "chrome")
         if (found := shutil.which(name))), None)
    if not browser:
        parser.error("Browser executable not found; select an existing runtime with --browser")
    try:
        result = capture(args.source, args.output, browser, args.width, args.height,
                         args.virtual_time_ms, args.timeout, args.browser_arg)
    except (OSError, ValueError) as exc:
        print(json.dumps({"passed": False, "failure": str(exc)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
