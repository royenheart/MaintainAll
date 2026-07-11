from __future__ import annotations

from pathlib import Path


def read_repo_file(path: str, *, repo_root: Path) -> str:
    root = Path(repo_root).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"path escapes repository root: {path}")
    return target.read_text()
