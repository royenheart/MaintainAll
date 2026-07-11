from __future__ import annotations

from pathlib import Path

from MaintainAll.paths import (
    history_dir,
    logs_dir,
    prompt_history_path,
    reports_dir,
    skills_dir,
)


def test_workspace_runtime_dirs_under_maintainall():
    ws = Path("/tmp/ws")
    assert reports_dir(ws) == Path("/tmp/ws/.maintainall/reports")
    assert logs_dir(ws) == Path("/tmp/ws/.maintainall/logs")
    assert history_dir(ws) == Path("/tmp/ws/.maintainall/history")
    assert prompt_history_path(ws) == Path("/tmp/ws/.maintainall/history/prompt.jsonl")


def test_skills_dir_still_under_agents():
    ws = Path("/tmp/ws")
    assert skills_dir(ws) == Path("/tmp/ws/.agents/skills")
