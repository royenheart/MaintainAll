from pathlib import Path

import pytest

from MaintainAll.missions.models import AllowedCommand
from MaintainAll.tools.fs import read_repo_file
from MaintainAll.tools.match import CommandGate
from MaintainAll.tools.shell import run_allowed


def test_gate_allows_and_counts():
    gate = CommandGate([AllowedCommand(pattern=r"^echo hi$", cwd=".")])
    assert gate.check("echo hi")
    assert gate.counts["^echo hi$"] == 1
    assert not gate.check("echo bye")
    assert not gate.check("bash -c 'echo hi'")


def test_run_allowed(tmp_path):
    gate = CommandGate([AllowedCommand(pattern=r"^echo hello$", cwd=".")])
    result = run_allowed("echo hello", gate=gate, repo_root=tmp_path)
    assert result.ok
    assert "hello" in result.stdout


def test_run_denied(tmp_path):
    gate = CommandGate([AllowedCommand(pattern=r"^echo hello$", cwd=".")])
    with pytest.raises(PermissionError):
        run_allowed("rm -rf /", gate=gate, repo_root=tmp_path)


def test_read_repo_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert read_repo_file("a.txt", repo_root=tmp_path) == "x"
