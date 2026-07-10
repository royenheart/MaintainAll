from __future__ import annotations

import json
from pathlib import Path

from MaintainAll.config import Settings
from MaintainAll.graph.nodes import mission_from_dict, mission_to_dict
from MaintainAll.graph.workflow import run_mission, run_session
from MaintainAll.memory.session import SessionMemory
from MaintainAll.missions.models import AllowedCommand, Expect, Mission, NotifyConfig, TaskNode


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLLM:
    """Queue-based fake chat model supporting ASSESS:/BOARD:/REACT: protocol."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    def invoke(self, messages):
        self.calls.append(list(messages))
        if not self.responses:
            raise AssertionError("FakeLLM response queue exhausted")
        return FakeMessage(self.responses.pop(0))


BOARD_MISSION = {
    "id": "fake-ok",
    "name": "Fake OK",
    "description": "one task mission",
    "skills": [],
    "schedule": None,
    "notify": {"on_complete": True, "on_failure": True},
    "allowed_commands": [],
    "tasks": [
        {
            "id": "t1",
            "name": "Say ok",
            "needs": [],
            "instruction": "produce ok",
            "expect": {"type": "contains", "patterns": ["ok"]},
        }
    ],
}


def test_happy_path_with_fake_llm(tmp_path: Path):
    llm = FakeLLM(
        [
            'ASSESS:{"feasible": true, "reason": "ok"}',
            f"BOARD:{json.dumps(BOARD_MISSION)}",
            "REACT:DECLARE_DONE",
        ]
    )
    settings = Settings(repo_path=str(tmp_path), agent_mode="restricted")
    memory = SessionMemory(mode="restricted")

    # skip_review via assess_fn not needed — use run_session with review_callback approve,
    # or invoke graph with skip_review through a thin wrapper.
    from MaintainAll.graph.workflow import build_graph

    app = build_graph(llm=llm)
    result = app.invoke(
        {
            "user_input": "do the ok thing",
            "mode": "restricted",
            "skip_review": True,
            "repo_path": str(tmp_path),
            "observations": [],
            "event_log": [],
            "messages": [],
            "rebuild_board": False,
            "react_done": False,
            "review_action": None,
            "review_feedback": "",
            "interrupt": None,
        }
    )

    assert result.get("feasible") is True
    assert result.get("validation_ok") is True
    report_path = result.get("report_path")
    assert report_path
    path = Path(report_path)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "fake-ok" in text
    assert "ok" in text.lower() or "Observations" in text


def test_assess_infeasible_no_report(tmp_path: Path):
    llm = FakeLLM(
        [
            'ASSESS:{"feasible": false, "reason": "out of scope"}',
        ]
    )
    from MaintainAll.graph.workflow import build_graph

    app = build_graph(llm=llm)
    result = app.invoke(
        {
            "user_input": "hack the planet",
            "mode": "restricted",
            "skip_review": True,
            "repo_path": str(tmp_path),
            "observations": [],
            "event_log": [],
            "messages": [],
            "rebuild_board": False,
            "react_done": False,
            "review_action": None,
            "review_feedback": "",
            "interrupt": None,
        }
    )

    assert result.get("feasible") is False
    assert result.get("reject_reason") == "out of scope"
    assert not result.get("report_path")
    assert not list((tmp_path / ".agents" / "reports").glob("*.md"))


def test_run_session_with_review_callback(tmp_path: Path):
    llm = FakeLLM(
        [
            'ASSESS:{"feasible": true, "reason": "ok"}',
            f"BOARD:{json.dumps(BOARD_MISSION)}",
            "REACT:DECLARE_DONE",
        ]
    )
    settings = Settings(repo_path=str(tmp_path), agent_mode="restricted")
    memory = SessionMemory(mode="restricted")

    def review_cb(state):
        assert state.get("interrupt") == "review"
        assert state.get("mission_draft")
        return {"action": "approve", "feedback": ""}

    result = run_session(
        "do the ok thing",
        settings=settings,
        memory=memory,
        review_callback=review_cb,
        llm=llm,
    )
    assert result.get("validation_ok") is True
    assert result.get("report_path")
    assert memory.last_report is not None


def test_run_mission_skips_review(tmp_path: Path):
    mission = Mission(
        id="cron-job",
        name="Cron",
        description="d",
        skills=[],
        schedule=None,
        notify=NotifyConfig(),
        allowed_commands=[AllowedCommand(pattern=r"^echo ok$", cwd=".")],
        tasks=[
            TaskNode(
                id="t1",
                name="Echo",
                needs=[],
                instruction="echo",
                expect=Expect(type="contains", patterns=["ok"]),
                script="echo ok",
            )
        ],
    )
    settings = Settings(repo_path=str(tmp_path), agent_mode="restricted")
    # No LLM: react runs script via gate
    result = run_mission(mission, settings=settings, skip_review=True, llm=None)
    assert result.get("mode") == "mission"
    assert result.get("validation_ok") is True
    assert result.get("report_path")
    assert Path(result["report_path"]).exists()


def test_mission_dict_roundtrip():
    mission = Mission(
        id="rt",
        name="RT",
        description="d",
        skills=["s"],
        schedule=None,
        notify=NotifyConfig(),
        allowed_commands=[],
        tasks=[
            TaskNode(
                id="a",
                name="A",
                needs=[],
                instruction="i",
                expect=Expect(type="contains", patterns=["x"]),
                status="done",
            )
        ],
    )
    data = mission_to_dict(mission)
    assert data["tasks"][0]["status"] == "done"
    restored = mission_from_dict(data)
    assert restored.id == "rt"
    assert restored.tasks[0].status == "done"
