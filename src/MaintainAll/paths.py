from __future__ import annotations

import os
from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_repo_path() -> Path:
    return package_root()


def agents_dir(repo: Path | None = None) -> Path:
    return (repo or default_repo_path()) / ".agents"


def skills_dir(repo: Path | None = None) -> Path:
    return agents_dir(repo) / "skills"


def missions_dir(repo: Path | None = None) -> Path:
    return agents_dir(repo) / "missions"


def reports_dir(repo: Path | None = None) -> Path:
    return agents_dir(repo) / "reports"


def config_dir() -> Path:
    override = os.environ.get("MAINTAINALL_CONFIG_DIR")
    if override:
        return Path(override)
    from platformdirs import user_config_dir

    return Path(user_config_dir("maintainall"))
