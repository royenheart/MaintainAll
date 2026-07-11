from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from dataclasses import dataclass

from MaintainAll.config import Settings, effective_trusted_dirs, load_settings, normalize_dir
from MaintainAll.cron.schedule import next_run, local_now, to_local, format_local_stamp
from MaintainAll.graph.workflow import run_mission
from MaintainAll.missions.loader import load_missions
from MaintainAll.missions.models import Mission
from MaintainAll.notify.report import format_mission_report, write_report
from MaintainAll.paths import (
    agents_dir,
    daemon_locks_dir,
    daemon_state_path,
    missions_dir,
    reports_dir,
)

SCAN_INTERVAL_SECONDS = 30
LEGACY_STATE_FILENAME = ".daemon_state.json"


def mission_runtime_key(repo: Path | str, mission_id: str) -> str:
    """Composite identity: absolute workspace + mission id."""
    root = normalize_dir(repo)
    return f"{root}::{mission_id}"


def lock_filename_for_key(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return f"{digest}.lock"


def locks_dir(*, data_dir: str | Path | None = None) -> Path:
    return daemon_locks_dir(data_dir=data_dir)


def _state_path(*, data_dir: str | Path | None = None) -> Path:
    return daemon_state_path(data_dir=data_dir)


def _legacy_state_path(repo: Path) -> Path:
    return agents_dir(repo) / LEGACY_STATE_FILENAME


def load_daemon_state(*, data_dir: str | Path | None = None) -> dict[str, str]:
    path = _state_path(data_dir=data_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_daemon_state(
    state: dict[str, str], *, data_dir: str | Path | None = None
) -> None:
    path = _state_path(data_dir=data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _load_legacy_repo_state(repo: Path) -> dict[str, str]:
    path = _legacy_state_path(repo)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def migrate_legacy_daemon_state(
    state: dict[str, str],
    repos: list[Path],
) -> dict[str, str]:
    """Fold per-repo `.agents/.daemon_state.json` into composite keys (once)."""
    out = dict(state)
    for repo in repos:
        if not repo.is_dir():
            continue
        legacy = _load_legacy_repo_state(repo)
        for mission_id, ts in legacy.items():
            if not isinstance(mission_id, str) or not isinstance(ts, str):
                continue
            key = mission_runtime_key(repo, mission_id)
            if key not in out:
                out[key] = ts
    return out


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
    """Return True when the next cron tick after *last_run* is at or before *now*.

    If the mission has never been armed (``last_run is None``), it is **not** due.
    The daemon must first record ``last_run = now`` without executing — otherwise a
    fresh weekly/monthly schedule would catch up from the epoch and fire immediately.
    """
    if last_run is None:
        return False
    when = to_local(now)
    base = to_local(last_run)
    return next_run(schedule, base) <= when


def schedule_base_time(
    now: datetime, last_run: datetime | None
) -> datetime:
    """Anchor for ``next_run`` / UI preview: last run if armed, else *now*."""
    when = to_local(now)
    if last_run is None:
        return when
    return to_local(last_run)


@dataclass
class ScheduledMissionView:
    """Read-only view of a mission under a trusted workspace (for /cron UI)."""

    repo: Path
    mission: Mission
    runtime_key: str
    schedule: str | None
    last_run: datetime | None
    next_run_at: datetime | None
    due: bool

    @property
    def mission_id(self) -> str:
        return self.mission.id


def _short_repo(repo: Path) -> str:
    home = str(Path.home())
    text = str(repo)
    if text.startswith(home):
        return "~" + text[len(home) :]
    return text


def format_mission_schedule_line(view: ScheduledMissionView) -> str:
    sched = view.schedule or "—"
    nxt = format_local_stamp(view.next_run_at) if view.next_run_at else "—"
    due = " due" if view.due else ""
    return f"{view.mission.id} @ {_short_repo(view.repo)} · {sched} · next {nxt}{due}"


def list_trusted_missions(
    settings: Settings,
    *,
    now: datetime | None = None,
) -> list[ScheduledMissionView]:
    """List all missions under trusted_dirs with schedule / next-run info."""
    when = to_local(now) if now is not None else local_now()
    trusted = [Path(p) for p in effective_trusted_dirs(settings)]
    state = load_daemon_state(data_dir=settings.data_dir)
    state = migrate_legacy_daemon_state(state, trusted)
    views: list[ScheduledMissionView] = []
    for repo in trusted:
        if not repo.is_dir():
            continue
        try:
            missions = load_missions(missions_dir(repo))
        except Exception:
            continue
        for mission in missions:
            key = mission_runtime_key(repo, mission.id)
            last = _parse_last_run(state.get(key))
            schedule = mission.schedule
            nxt: datetime | None = None
            due = False
            if schedule:
                try:
                    base = schedule_base_time(when, last)
                    nxt = to_local(next_run(schedule, base))
                    due = is_mission_due(schedule, when, last)
                except Exception:
                    nxt = None
                    due = False
            views.append(
                ScheduledMissionView(
                    repo=repo.resolve(),
                    mission=mission,
                    runtime_key=key,
                    schedule=schedule,
                    last_run=last,
                    next_run_at=nxt,
                    due=due,
                )
            )
    views.sort(key=lambda v: (str(v.repo), v.mission.id))
    return views


def daemon_status(settings: Settings) -> dict[str, Any]:
    """Best-effort status for the user systemd unit + local state."""
    unit = "maintainall-agent"
    active = "unknown"
    try:
        import subprocess

        proc = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        active = (proc.stdout or proc.stderr or "").strip() or "unknown"
    except Exception:
        active = "unknown"
    trusted = effective_trusted_dirs(settings)
    state_path = daemon_state_path(data_dir=settings.data_dir)
    return {
        "unit": unit,
        "active": active,
        "trusted_dirs": trusted,
        "trusted_count": len(trusted),
        "data_dir": settings.data_dir,
        "state_path": str(state_path),
        "state_exists": state_path.exists(),
    }


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
    state = dict(result)
    if "mission_draft" not in state:
        state["mission_draft"] = {
            "id": mission.id,
            "name": mission.name,
            "description": mission.description,
            "allowed_commands": [
                {"pattern": c.pattern, "cwd": c.cwd} for c in mission.allowed_commands
            ],
            "tasks": [],
        }
    body = format_mission_report(state)
    workspace = state.get("repo_path") or ""
    if workspace:
        return f"Workspace: {workspace}\n\n{body}"
    return body


def _maybe_notify(
    mission: Mission, body: str, result: dict[str, Any], settings: Settings
) -> None:
    from MaintainAll.notify.mail import mail_notify_allowed, maybe_notify_mission

    if not mail_notify_allowed():
        return
    maybe_notify_mission(
        draft={
            "id": mission.id,
            "notify": {
                "on_complete": mission.notify.on_complete,
                "on_failure": mission.notify.on_failure,
            },
        },
        validation_ok=result.get("validation_ok"),
        body=body,
        settings=settings,
    )


def _run_mission_in_repo(
    mission: Mission,
    *,
    repo: Path,
    settings: Settings,
) -> dict[str, Any]:
    """Run mission with settings.repo_path set to *repo* (and chdir for relative cmds)."""
    repo_settings = settings.model_copy(update={"repo_path": str(repo.resolve())})
    llm = None
    key = repo_settings.api_key.get_secret_value() if repo_settings.api_key else None
    if key:
        from MaintainAll.graph.llm import build_chat_model

        try:
            llm = build_chat_model(repo_settings)
        except Exception:
            llm = None
    prev = Path.cwd()
    try:
        os.chdir(repo)
        return run_mission(
            mission, settings=repo_settings, skip_review=True, llm=llm
        )
    finally:
        os.chdir(prev)


def scan_once(settings: Settings) -> None:
    trusted = [Path(p) for p in effective_trusted_dirs(settings)]
    now = local_now()
    data_dir = settings.data_dir
    state = load_daemon_state(data_dir=data_dir)
    before_keys = set(state.keys())
    state = migrate_legacy_daemon_state(state, trusted)
    migrated = set(state.keys()) != before_keys
    dirty = False

    for repo in trusted:
        if not repo.is_dir():
            continue
        try:
            scheduled = [m for m in load_missions(missions_dir(repo)) if m.schedule]
        except Exception:
            continue

        for mission in scheduled:
            key = mission_runtime_key(repo, mission.id)
            last_run = _parse_last_run(state.get(key))
            if last_run is None:
                # Arm cursor at first sight — do not catch up missed historical ticks.
                state[key] = now.isoformat()
                dirty = True
                continue
            if not is_mission_due(mission.schedule, now, last_run):
                continue

            lock = MissionLock(
                locks_dir(data_dir=data_dir) / lock_filename_for_key(key)
            )
            if not lock.acquire():
                continue

            try:
                result = _run_mission_in_repo(mission, repo=repo, settings=settings)
                body = format_report_body(mission, {**result, "repo_path": str(repo)})
                # Include workspace in report filename stem to disambiguate.
                report_stem = f"{mission.id}@{repo.name}"
                write_report(
                    report_stem,
                    body,
                    reports_dir(repo, data_dir=data_dir),
                )
                _maybe_notify(mission, body, result, settings)
                state[key] = now.isoformat()
                dirty = True
            finally:
                lock.release()

    if dirty or migrated:
        save_daemon_state(state, data_dir=data_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="MaintainAll scheduled mission daemon")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan then exit (for tests and manual runs)",
    )
    args = parser.parse_args()

    if args.once:
        scan_once(load_settings())
        return

    while True:
        # Reload each cycle so trusted_dirs / schedules pick up config edits.
        scan_once(load_settings())
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
