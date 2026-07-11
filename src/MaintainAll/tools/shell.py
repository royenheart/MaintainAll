from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from MaintainAll.tools.match import CommandGate, UnlimitedGate

Gate = CommandGate | UnlimitedGate


@dataclass
class RunResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int


def run_allowed(
    cmd: str,
    *,
    gate: Gate,
    repo_root: Path,
    dry_run: bool = False,
) -> RunResult:
    """Run ``cmd`` if the gate allows it.

    When ``dry_run`` is True (readonly agent mode), never call ``subprocess`` —
    return a failed result with a clear marker so validate does not pretend success.
    """
    if dry_run:
        return RunResult(
            ok=False,
            stdout="",
            stderr=f"[readonly] execution disabled: {cmd}",
            returncode=126,
        )

    if not gate.check(cmd):
        raise PermissionError(f"command not allowed: {cmd}")

    matched = gate.last_match
    if matched is None:
        raise PermissionError(f"command not allowed: {cmd}")

    repo_resolved = Path(repo_root).resolve()
    cwd = (repo_resolved / matched.cwd).resolve()
    if not cwd.is_relative_to(repo_resolved):
        raise PermissionError(f"cwd escapes repository root: {cwd}")
    completed = subprocess.run(
        shlex.split(cmd),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return RunResult(
        ok=completed.returncode == 0,
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )
