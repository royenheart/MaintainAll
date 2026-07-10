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


def test_fake_llm_react_run_executes(tmp_path: Path):
    mission = Mission(
        id="run-echo",
        name="Run echo",
        description="d",
        skills=[],
        schedule=None,
        notify=NotifyConfig(),
        allowed_commands=[AllowedCommand(pattern=r"^echo hello$", cwd=".")],
        tasks=[
            TaskNode(
                id="t1",
                name="Echo",
                needs=[],
                instruction="run echo hello",
                expect=Expect(type="contains", patterns=["hello"]),
            )
        ],
    )
    llm = FakeLLM(
        [
            "REACT:RUN:echo hello",
            "REACT:DECLARE_DONE",
        ]
    )
    settings = Settings(repo_path=str(tmp_path), agent_mode="restricted")
    events: list[dict] = []

    def on_event(ev):
        events.append(ev)

    result = run_mission(
        mission,
        settings=settings,
        skip_review=True,
        llm=llm,
        event_callback=on_event,
    )
    assert result.get("validation_ok") is True
    assert any("hello" in (o or "") for o in (result.get("observations") or []))
    assert any(e.get("type") == "cmd_count" for e in events)


def test_validate_uses_report_draft(tmp_path: Path):
    from MaintainAll.graph.nodes import validate_node

    draft = {
        "id": "rpt",
        "name": "R",
        "description": "d",
        "skills": [],
        "schedule": None,
        "notify": {"on_complete": True, "on_failure": True},
        "allowed_commands": [],
        "tasks": [
            {
                "id": "t1",
                "name": "Check section",
                "needs": [],
                "instruction": "write section",
                "expect": {"type": "report_section", "name": "connectivity"},
                "status": "done",
            }
        ],
    }
    result = validate_node(
        {
            "mission_draft": draft,
            "observations": [],
            "report_draft": "## connectivity\n\nok\n",
            "repo_path": str(tmp_path),
            "event_log": [],
        }
    )
    assert result["validation_ok"] is True


def test_fake_llm_observe_fills_report_draft(tmp_path: Path):
    mission = Mission(
        id="observe-rpt",
        name="Observe",
        description="d",
        skills=[],
        schedule=None,
        notify=NotifyConfig(),
        allowed_commands=[],
        tasks=[
            TaskNode(
                id="t1",
                name="Sections",
                needs=[],
                instruction="write report sections",
                expect=Expect(type="report_section", name="connectivity"),
            ),
            TaskNode(
                id="t2",
                name="CIDR",
                needs=["t1"],
                instruction="cidr",
                expect=Expect(type="report_section", name="cidr-diff"),
            ),
            TaskNode(
                id="t3",
                name="File",
                needs=["t2"],
                instruction="file",
                expect=Expect(
                    type="file_exists",
                    path_glob=".agents/reports/observe-rpt-*.md",
                ),
            ),
        ],
    )
    llm = FakeLLM(
        [
            "REACT:OBSERVE:## connectivity\nok\n## cidr-diff\ndiff\n",
            "REACT:DECLARE_DONE",
        ]
    )
    settings = Settings(repo_path=str(tmp_path), agent_mode="restricted")
    result = run_mission(mission, settings=settings, skip_review=True, llm=llm)
    assert result.get("validation_ok") is True
    assert "## connectivity" in (result.get("report_draft") or "")
    assert result.get("report_path")
    assert Path(result["report_path"]).exists()


def test_finalize_writes_report_when_validation_fails(tmp_path: Path):
    from MaintainAll.graph.workflow import build_graph

    # Mission expect will fail (missing pattern), but finalize must still run.
    mission_draft = {
        "id": "fail-rpt",
        "name": "Fail",
        "description": "d",
        "skills": [],
        "schedule": None,
        "notify": {"on_complete": True, "on_failure": True},
        "allowed_commands": [],
        "tasks": [
            {
                "id": "t1",
                "name": "Need missing",
                "needs": [],
                "instruction": "x",
                "expect": {"type": "contains", "patterns": ["NEVER_MATCH_THIS"]},
                "status": "done",
            }
        ],
    }
    llm = FakeLLM(
        [
            'ASSESS:{"feasible": true, "reason": "ok"}',
            f"BOARD:{json.dumps(mission_draft)}",
            "REACT:DECLARE_DONE",
            "REACT:DECLARE_DONE",  # retry after failed validate
        ]
    )
    app = build_graph(llm=llm)
    result = app.invoke(
        {
            "user_input": "fail please",
            "mode": "restricted",
            "skip_review": True,
            "repo_path": str(tmp_path),
            "observations": [],
            "report_draft": "",
            "event_log": [],
            "messages": [],
            "rebuild_board": False,
            "react_done": False,
            "review_action": None,
            "review_feedback": "",
            "interrupt": None,
        }
    )
    assert result.get("validation_ok") is False
    assert result.get("report_path")
    assert Path(result["report_path"]).exists()
    text = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "fail-rpt" in text
    assert "Validation Errors" in text or "NEVER_MATCH" in text
