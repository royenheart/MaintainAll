from __future__ import annotations

from pathlib import Path

from MaintainAll.missions.models import Expect


def evaluate_expect(
    expect: Expect,
    *,
    stdout: str,
    report_text: str,
    repo_root: Path,
) -> tuple[bool, str]:
    if expect.type == "contains":
        for pattern in expect.patterns:
            if pattern not in stdout:
                return False, f"stdout missing pattern: {pattern!r}"
        return True, ""

    if expect.type == "report_section":
        if not expect.name:
            return False, "report_section requires name"
        heading = f"## {expect.name}"
        if heading not in report_text:
            return False, f"report missing section: {heading!r}"
        return True, ""

    if expect.type == "file_exists":
        if not expect.path_glob:
            return False, "file_exists requires path_glob"
        if not list(repo_root.glob(expect.path_glob)):
            return False, f"no file matching {expect.path_glob!r} under {repo_root}"
        return True, ""

    return False, f"unknown expect type: {expect.type!r}"
