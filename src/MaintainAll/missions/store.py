from __future__ import annotations

from pathlib import Path

import yaml

from MaintainAll.missions.models import Expect, Mission, NotifyConfig, TaskNode


def _expect_to_dict(expect: Expect) -> dict:
    data: dict = {"type": expect.type}
    if expect.patterns:
        data["patterns"] = expect.patterns
    if expect.name is not None:
        data["name"] = expect.name
    if expect.path_glob is not None:
        data["path_glob"] = expect.path_glob
    return data


def _task_to_dict(task: TaskNode) -> dict:
    data: dict = {
        "id": task.id,
        "name": task.name,
        "needs": task.needs,
        "instruction": task.instruction,
        "expect": _expect_to_dict(task.expect),
    }
    if task.script is not None:
        data["script"] = task.script
    if task.tasks:
        data["tasks"] = [_task_to_dict(child) for child in task.tasks]
    return data


def _notify_to_dict(notify: NotifyConfig) -> dict:
    return {
        "on_complete": notify.on_complete,
        "on_failure": notify.on_failure,
    }


def _mission_to_dict(mission: Mission) -> dict:
    return {
        "id": mission.id,
        "name": mission.name,
        "description": mission.description,
        "skills": mission.skills,
        "schedule": mission.schedule,
        "notify": _notify_to_dict(mission.notify),
        "allowed_commands": [
            {"pattern": cmd.pattern, "cwd": cmd.cwd}
            for cmd in mission.allowed_commands
        ],
        "tasks": [_task_to_dict(task) for task in mission.tasks],
    }


def solidify_mission(mission: Mission, *, missions_root: Path) -> Path:
    mission_dir = missions_root / mission.id
    mission_dir.mkdir(parents=True, exist_ok=True)
    path = mission_dir / "MISSION.yaml"
    path.write_text(
        yaml.safe_dump(
            _mission_to_dict(mission),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return path


def update_mission_schedule(
    repo: Path,
    mission_id: str,
    schedule: str | None,
) -> Path:
    """Update ``schedule`` in ``.agents/missions/<id>/MISSION.yaml`` under *repo*."""
    from MaintainAll.paths import missions_dir

    path = missions_dir(Path(repo)) / mission_id / "MISSION.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Mission YAML not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid mission YAML: {path}")
    text = (schedule or "").strip()
    data["schedule"] = text if text else None
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path
