from __future__ import annotations

from pathlib import Path

import yaml

from MaintainAll.missions.models import (
    AllowedCommand,
    Expect,
    Mission,
    NotifyConfig,
    TaskNode,
)


class MissionValidationError(ValueError):
    pass


def _parse_expect(data: dict) -> Expect:
    return Expect(
        type=data["type"],
        patterns=data.get("patterns", []),
        name=data.get("name"),
        path_glob=data.get("path_glob"),
    )


def _parse_task(data: dict) -> TaskNode:
    return TaskNode(
        id=data["id"],
        name=data["name"],
        needs=list(data.get("needs", [])),
        instruction=data["instruction"],
        expect=_parse_expect(data["expect"]),
        script=data.get("script"),
        tasks=[_parse_task(child) for child in data.get("tasks", [])],
    )


def _flatten_tasks(tasks: list[TaskNode]) -> list[TaskNode]:
    flat: list[TaskNode] = []
    for task in tasks:
        flat.append(task)
        flat.extend(_flatten_tasks(task.tasks))
    return flat


def _validate_dag(tasks: list[TaskNode]) -> None:
    flat = _flatten_tasks(tasks)
    ids = {task.id for task in flat}

    for task in flat:
        for need in task.needs:
            if need not in ids:
                raise MissionValidationError(
                    f"Unknown dependency '{need}' for task '{task.id}'"
                )

    in_degree = {task.id: 0 for task in flat}
    children: dict[str, list[str]] = {task.id: [] for task in flat}
    for task in flat:
        for need in task.needs:
            children[need].append(task.id)
            in_degree[task.id] += 1

    queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
    visited = 0
    while queue:
        task_id = queue.pop(0)
        visited += 1
        for child in children[task_id]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if visited != len(flat):
        raise MissionValidationError("Cycle detected in task dependencies")


def _parse_mission(data: dict) -> Mission:
    notify_data = data.get("notify") or {}
    notify = NotifyConfig(
        on_complete=notify_data.get("on_complete", True),
        on_failure=notify_data.get("on_failure", True),
    )
    allowed_commands = [
        AllowedCommand(
            pattern=item["pattern"],
            cwd=item.get("cwd", "."),
        )
        for item in data.get("allowed_commands", [])
    ]
    tasks = [_parse_task(item) for item in data.get("tasks", [])]
    _validate_dag(tasks)
    return Mission(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        skills=list(data.get("skills", [])),
        schedule=data.get("schedule"),
        notify=notify,
        allowed_commands=allowed_commands,
        tasks=tasks,
    )


def load_mission(path: Path) -> Mission:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MissionValidationError(f"Invalid mission file: {path}")
    return _parse_mission(data)


def load_missions(root: Path) -> list[Mission]:
    if not root.exists():
        return []
    return [load_mission(path) for path in sorted(root.glob("*/MISSION.yaml"))]


def runnable_tasks(mission: Mission) -> list[TaskNode]:
    done_ids = {
        task.id
        for task in _flatten_tasks(mission.tasks)
        if task.status == "done"
    }
    return [
        task
        for task in mission.tasks
        if task.status == "pending" and all(need in done_ids for need in task.needs)
    ]
