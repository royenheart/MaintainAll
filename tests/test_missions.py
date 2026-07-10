from pathlib import Path

import pytest

from MaintainAll.missions.loader import (
    MissionValidationError,
    load_mission,
    load_missions,
    runnable_tasks,
)
from MaintainAll.missions.models import AllowedCommand, Expect, Mission, NotifyConfig, TaskNode
from MaintainAll.missions.store import solidify_mission

FIXTURES = Path(__file__).parent / "fixtures" / "missions"


def test_load_mission_dag():
    m = load_mission(FIXTURES / "demo" / "MISSION.yaml")
    assert m.id == "demo"
    assert [t.id for t in m.tasks] == ["a", "b"]
    assert m.tasks[1].needs == ["a"]


def test_cycle_rejected(tmp_path):
    p = tmp_path / "MISSION.yaml"
    p.write_text("""
id: bad
name: bad
description: x
skills: []
allowed_commands: []
tasks:
  - id: a
    name: A
    needs: [b]
    instruction: x
    expect: {type: contains, patterns: [x]}
  - id: b
    name: B
    needs: [a]
    instruction: x
    expect: {type: contains, patterns: [x]}
""")
    with pytest.raises(MissionValidationError):
        load_mission(p)


def test_solidify(tmp_path):
    m = Mission(
        id="new-one",
        name="New",
        description="d",
        skills=[],
        schedule=None,
        notify=NotifyConfig(),
        allowed_commands=[AllowedCommand(pattern=r"^true$", cwd=".")],
        tasks=[
            TaskNode(
                id="t1",
                name="T",
                needs=[],
                instruction="i",
                expect=Expect(type="contains", patterns=["ok"]),
            )
        ],
    )
    path = solidify_mission(m, missions_root=tmp_path)
    assert path.exists()
    loaded = load_mission(path)
    assert loaded.id == "new-one"


def test_load_missions(tmp_path):
    demo_src = FIXTURES / "demo" / "MISSION.yaml"
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / "MISSION.yaml").write_text(demo_src.read_text(encoding="utf-8"))
    missions = load_missions(tmp_path)
    assert len(missions) == 1
    assert missions[0].id == "demo"


def test_runnable_tasks_nested_child():
    parent = TaskNode(
        id="parent",
        name="Parent",
        needs=[],
        instruction="parent",
        expect=Expect(type="contains", patterns=["ok"]),
        status="done",
        tasks=[
            TaskNode(
                id="child",
                name="Child",
                needs=["parent"],
                instruction="child",
                expect=Expect(type="contains", patterns=["ok"]),
            )
        ],
    )
    mission = Mission(
        id="nested",
        name="Nested",
        description="d",
        skills=[],
        schedule=None,
        notify=NotifyConfig(),
        allowed_commands=[],
        tasks=[parent],
    )
    assert [t.id for t in runnable_tasks(mission)] == ["child"]


def test_unknown_dependency_rejected(tmp_path):
    p = tmp_path / "MISSION.yaml"
    p.write_text("""
id: bad
name: bad
description: x
skills: []
allowed_commands: []
tasks:
  - id: a
    name: A
    needs: [missing]
    instruction: x
    expect: {type: contains, patterns: [x]}
""")
    with pytest.raises(MissionValidationError, match="Unknown dependency"):
        load_mission(p)


def test_solidify_roundtrip_preserves_commands_and_task_ids(tmp_path):
    pattern = r"^pytest\b"
    m = Mission(
        id="roundtrip",
        name="Roundtrip",
        description="d",
        skills=["skill-a"],
        schedule="0 * * * *",
        notify=NotifyConfig(on_complete=False, on_failure=True),
        allowed_commands=[AllowedCommand(pattern=pattern, cwd="/tmp")],
        tasks=[
            TaskNode(
                id="root",
                name="Root",
                needs=[],
                instruction="root",
                expect=Expect(type="contains", patterns=["root"]),
                tasks=[
                    TaskNode(
                        id="nested-1",
                        name="Nested",
                        needs=["root"],
                        instruction="nested",
                        expect=Expect(type="contains", patterns=["nested"]),
                    )
                ],
            )
        ],
    )
    path = solidify_mission(m, missions_root=tmp_path)
    loaded = load_mission(path)
    assert loaded.id == "roundtrip"
    assert len(loaded.allowed_commands) == 1
    assert loaded.allowed_commands[0].pattern == pattern
    assert loaded.allowed_commands[0].cwd == "/tmp"

    def collect_ids(tasks: list[TaskNode]) -> list[str]:
        ids: list[str] = []
        for task in tasks:
            ids.append(task.id)
            ids.extend(collect_ids(task.tasks))
        return ids

    assert collect_ids(loaded.tasks) == ["root", "nested-1"]
