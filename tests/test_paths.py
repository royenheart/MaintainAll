from pathlib import Path

from MaintainAll.paths import (
    default_data_dir,
    history_dir,
    logs_dir,
    prompt_history_path,
    reports_dir,
    workspace_data_dir,
)


def test_default_data_dir_is_home_maintainall():
    assert default_data_dir() == Path.home() / ".maintainall"
    assert workspace_data_dir() == Path.home() / ".maintainall"


def test_explicit_data_dir_overrides(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MAINTAINALL_DATA_DIR", raising=False)
    custom = tmp_path / "data"
    assert workspace_data_dir(data_dir=custom) == custom
    assert reports_dir(data_dir=custom) == custom / "reports"
    assert logs_dir(data_dir=custom) == custom / "logs"
    assert history_dir(data_dir=custom) == custom / "history"
    assert prompt_history_path(data_dir=custom) == custom / "history" / "prompt.jsonl"


def test_env_data_dir_overrides_default(tmp_path: Path, monkeypatch):
    custom = tmp_path / "envdata"
    monkeypatch.setenv("MAINTAINALL_DATA_DIR", str(custom))
    assert workspace_data_dir() == custom
