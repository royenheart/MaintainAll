from pathlib import Path

from MaintainAll.memory.session import SessionMemory
from MaintainAll.missions.models import Mission, NotifyConfig


def test_add_message():
    mem = SessionMemory()
    mem.add_message("user", "hello")
    mem.add_message("assistant", "hi")
    assert mem.messages == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_clear():
    mem = SessionMemory()
    mem.add_message("user", "hello")
    mem.mission = Mission(
        id="m1",
        name="M",
        description="d",
        skills=[],
        schedule=None,
        notify=NotifyConfig(),
        allowed_commands=[],
        tasks=[],
    )
    mem.command_counts["echo"] = 2
    mem.last_report = Path("/tmp/report.md")
    mem.assess_notes = "notes"
    mem.mode = "restricted"

    mem.clear()

    assert mem.messages == []
    assert mem.mission is None
    assert mem.command_counts == {}
    assert mem.last_report is None
    assert mem.assess_notes == ""
    assert mem.mode == "readonly"
