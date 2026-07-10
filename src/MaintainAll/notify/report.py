from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def write_report(mission_id: str, body: str, reports_root: Path) -> Path:
    reports_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = reports_root / f"{mission_id}-{ts}.md"
    path.write_text(body, encoding="utf-8")
    return path
