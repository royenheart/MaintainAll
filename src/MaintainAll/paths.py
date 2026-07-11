from __future__ import annotations

import os
from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_repo_path() -> Path:
    return package_root()


def default_data_dir() -> Path:
    """Default runtime data root (reports / logs / history)."""
    return Path.home() / ".maintainall"


def agents_dir(repo: Path | None = None) -> Path:
    """Versioned agent assets (skills / missions) under the workspace."""
    return (repo or default_repo_path()) / ".agents"


def workspace_data_dir(
    repo: Path | None = None,
    *,
    data_dir: str | Path | None = None,
) -> Path:
    """Runtime data root (not version-controlled).

    Resolution order:
    1. Explicit *data_dir* argument
    2. ``MAINTAINALL_DATA_DIR`` environment variable
    3. Default ``~/.maintainall``

    The *repo* argument is kept for call-site compatibility but no longer
    places data under ``<repo>/.maintainall`` (use *data_dir* to override).

    Layout::

        ~/.maintainall/   (or configured data_dir)
          reports/
          logs/
          history/
    """
    if data_dir is not None and str(data_dir).strip():
        return Path(str(data_dir)).expanduser()
    env = os.environ.get("MAINTAINALL_DATA_DIR")
    if env and env.strip():
        return Path(env.strip()).expanduser()
    return default_data_dir()


def skills_dir(repo: Path | None = None) -> Path:
    return agents_dir(repo) / "skills"


def missions_dir(repo: Path | None = None) -> Path:
    return agents_dir(repo) / "missions"


def reports_dir(
    repo: Path | None = None,
    *,
    data_dir: str | Path | None = None,
) -> Path:
    return workspace_data_dir(repo, data_dir=data_dir) / "reports"


def logs_dir(
    repo: Path | None = None,
    *,
    data_dir: str | Path | None = None,
) -> Path:
    return workspace_data_dir(repo, data_dir=data_dir) / "logs"


def history_dir(
    repo: Path | None = None,
    *,
    data_dir: str | Path | None = None,
) -> Path:
    return workspace_data_dir(repo, data_dir=data_dir) / "history"


def prompt_history_path(
    repo: Path | None = None,
    *,
    data_dir: str | Path | None = None,
) -> Path:
    return history_dir(repo, data_dir=data_dir) / "prompt.jsonl"


def daemon_state_path(*, data_dir: str | Path | None = None) -> Path:
    """Global daemon last-run map (composite keys), under the runtime data dir."""
    return workspace_data_dir(data_dir=data_dir) / "daemon_state.json"


def daemon_locks_dir(*, data_dir: str | Path | None = None) -> Path:
    """Global daemon flock directory under the runtime data dir."""
    return workspace_data_dir(data_dir=data_dir) / "locks"


def config_dir() -> Path:
    override = os.environ.get("MAINTAINALL_CONFIG_DIR")
    if override:
        return Path(override)
    from platformdirs import user_config_dir

    return Path(user_config_dir("maintainall"))
