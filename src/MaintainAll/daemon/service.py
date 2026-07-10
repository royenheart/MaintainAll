from __future__ import annotations

import argparse
import fcntl
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from MaintainAll.config import Settings, load_settings
from MaintainAll.cron.schedule import next_run
from MaintainAll.graph.workflow import run_mission
from MaintainAll.missions.loader import load_missions
from MaintainAll.missions.models import Mission
from MaintainAll.notify.mail import send_notification
from MaintainAll.notify.report import write_report
from MaintainAll.paths import agents_dir, missions_dir, reports_dir

SCAN_INTERVAL_SECONDS = 30
STATE_FILENAME = ".daemon_state.json"


def locks_dir(repo: Path) -> Path:
    return agents_dir(repo) / ".locks"


def _state_path(repo: Path) -> Path:
    return agents_dir(repo) / STATE_FILENAME


def load_daemon_state(repo: Path) -> dict[str, str]:
    path = _state_path(repo)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_daemon_state(repo: Path, state: dict[str, str]) -> None:
    path = _state_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _parse_last_run(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_mission_due(
    schedule: str, now: datetime, last_run: datetime | None
) -> bool:
    base = last_run or datetime(1970, 1, 1, tzinfo=timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return next_run(schedule, base) <= now


class MissionLock:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._fd: int | None = None
        self._file = None

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.lock_path, "w", encoding="utf-8")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._file.close()
            self._file = None
            return False
        self._file.write(str(os.getpid()))
        self._file.flush()
        self._fd = self._file.fileno()
        return True

    def release(self) -> None:
        if self._file is None:
            return
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None
            self._fd = None


def format_report_body(mission: Mission, result: dict[str, Any]) -> str:
    observations = result.get("observations") or []
    obs_lines = [f"- {obs}" for obs in observations] or ["- (none)"]
    lines = [
        f"# Mission Report: {mission.id}",
        "",
        f"- name: {mission.name}",
        f"- schedule: {mission.schedule or '(none)'}",
        f"- validation_ok: {result.get('validation_ok')}",
        "",
        "## Observations",
        "",
        *obs_lines,
        "",
    ]
    if result.get("validation_errors"):
        lines.extend(["## Validation Errors", ""])
        lines.extend(f"- {err}" for err in result["validation_errors"])
        lines.append("")
    return "\n".join(lines)


def _maybe_notify(
    mission: Mission, body: str, result: dict[str, Any], settings: Settings
) -> None:
    ok = bool(result.get("validation_ok"))
    if ok and not mission.notify.on_complete:
        return
    if not ok and not mission.notify.on_failure:
        return
    status = "OK" if ok else "FAILED"
    subject = f"MaintainAll mission {mission.id}: {status}"
    send_notification(subject, body, settings)


def scan_once(settings: Settings) -> None:
    repo = Path(settings.repo_path)
    now = datetime.now(timezone.utc)
    state = load_daemon_state(repo)
    scheduled = [m for m in load_missions(missions_dir(repo)) if m.schedule]

    for mission in scheduled:
        last_run = _parse_last_run(state.get(mission.id))
        if not is_mission_due(mission.schedule, now, last_run):
            continue

        lock = MissionLock(locks_dir(repo) / f"{mission.id}.lock")
        if not lock.acquire():
            continue

        try:
            result = run_mission(mission, settings=settings, skip_review=True)
            body = format_report_body(mission, result)
            write_report(mission.id, body, reports_dir(repo))
            _maybe_notify(mission, body, result, settings)
            state[mission.id] = now.isoformat()
            save_daemon_state(repo, state)
        finally:
            lock.release()


def main() -> None:
    parser = argparse.ArgumentParser(description="MaintainAll scheduled mission daemon")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan then exit (for tests and manual runs)",
    )
    args = parser.parse_args()

    settings = load_settings()
    if args.once:
        scan_once(settings)
        return

    while True:
        scan_once(settings)
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
