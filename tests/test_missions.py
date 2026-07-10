from pathlib import Path

import pytest

from MaintainAll.missions.loader import MissionValidationError, load_mission, load_missions
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
