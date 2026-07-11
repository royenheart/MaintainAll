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
    "allowed_commands": [{"pattern": r"^echo\b", "cwd": "."}],
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


def test_assess_prompt_includes_mode(tmp_path: Path):
    llm = FakeLLM(
        [
            'ASSESS:{"feasible": false, "reason": "readonly 无法执行 bash -n"}',
        ]
    )
    from MaintainAll.graph.nodes import make_nodes

    nodes = make_nodes(llm=llm)
    out = nodes["assess"](
        {
            "user_input": "用 bash -n 检查 maintaince 下所有脚本",
            "mode": "readonly",
            "report_language": "zh-CN",
            "repo_path": str(tmp_path),
            "event_log": [],
        }
    )
    assert out.get("feasible") is False
    assert "readonly" in str(out.get("reject_reason") or "").lower() or out.get(
        "reject_reason"
    )
    assert llm.calls, "assess should call LLM"
    system = llm.calls[0][0]["content"]
    user = llm.calls[0][1]["content"]
    assert "Agent mode: readonly" in user
    assert "Report language: zh-CN" in user
    assert "readonly" in system.lower()
    assert "feasible" in system.lower()
    assert "zh-CN" in system


def test_finalize_offers_solidify_when_validation_fails(tmp_path: Path):
    from MaintainAll.graph.nodes import finalize_node

    out = finalize_node(
        {
            "user_input": "check scripts",
            "mode": "readonly",
            "skip_review": False,
            "repo_path": str(tmp_path),
            "mission_draft": BOARD_MISSION,
            "validation_ok": False,
            "validation_errors": ["main: report missing section"],
            "observations": [],
            "report_draft": "",
            "event_log": [],
        }
    )
    assert out.get("interrupt") == "solidify"
    assert out.get("report_path")
    assert Path(out["report_path"]).exists()


def test_run_session_preserves_solidify_interrupt(tmp_path: Path):
    """_finish_session must not wipe finalize's solidify interrupt."""
    llm = FakeLLM(
        [
            'ASSESS:{"feasible": true, "reason": "ok"}',
            f"BOARD:{json.dumps(BOARD_MISSION)}",
            "REACT:DECLARE_DONE",
        ]
    )
    settings = Settings(repo_path=str(tmp_path), agent_mode="restricted")
    memory = SessionMemory(mode="restricted")
    result = run_session(
        "do the ok thing",
        settings=settings,
        memory=memory,
        llm=llm,
        skip_review=False,
        review_callback=lambda _state: {"action": "approve", "feedback": ""},
    )
    assert result.get("interrupt") == "solidify"
    assert memory.mission is not None
    assert memory.mission.id == "fake-ok"


def test_finalize_skips_solidify_for_mission_mode(tmp_path: Path):
    from MaintainAll.graph.nodes import finalize_node

    out = finalize_node(
        {
            "user_input": "run mission",
            "mode": "mission",
            "skip_review": True,
            "repo_path": str(tmp_path),
            "mission_draft": BOARD_MISSION,
            "validation_ok": True,
            "observations": ["ok"],
            "report_draft": "",
            "event_log": [],
        }
    )
    assert out.get("interrupt") is None


def test_run_session_reject_ends_without_rebuild(tmp_path: Path):
    llm = FakeLLM(
        [
            'ASSESS:{"feasible": true, "reason": "ok"}',
            f"BOARD:{json.dumps(BOARD_MISSION)}",
        ]
    )
    settings = Settings(repo_path=str(tmp_path), agent_mode="restricted")
    memory = SessionMemory(mode="restricted")
    events: list[dict] = []

    def review_cb(state):
        assert state.get("interrupt") == "review"
        return {"action": "reject", "feedback": "nope"}

    result = run_session(
        "do the ok thing",
        settings=settings,
        memory=memory,
        review_callback=review_cb,
        event_callback=events.append,
        llm=llm,
    )
    assert result.get("review_action") == "reject"
    reason = str(result.get("reject_reason") or "")
    assert "nope" in reason or "User rejected" in reason
    assert len(llm.calls) == 2
    assert any(e.get("type") == "reject" for e in events)
    board_thinking = [
        e for e in events if e.get("type") == "thinking_start" and e.get("phase") == "board"
    ]
    assert len(board_thinking) <= 1


def test_run_session_preloaded_mission_skips_board_llm(tmp_path: Path):
    """``/run`` path: preloaded draft + mode=mission must not call board LLM."""
    llm = FakeLLM(
        [
            "REACT:DECLARE_DONE",
        ]
    )
    settings = Settings(repo_path=str(tmp_path), agent_mode="restricted")
    memory = SessionMemory(mode="restricted")

    def review_cb(state):
        assert state.get("mission_draft", {}).get("id") == "fake-ok"
        return {"action": "approve", "feedback": ""}

    result = run_session(
        "run mission fake-ok",
        settings=settings,
        memory=memory,
        review_callback=review_cb,
        llm=llm,
        mission_draft=BOARD_MISSION,
        mode="mission",
        skip_review=False,
        feasible=True,
    )
    assert result.get("mode") == "mission"
    assert result.get("mission_draft", {}).get("id") == "fake-ok"
    # Only react (no assess/board LLM calls)
    assert len(llm.calls) == 1
    assert result.get("validation_ok") is True


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
                    path_glob=".maintainall/reports/observe-rpt-*.md",
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
        "allowed_commands": [{"pattern": r"^echo\b", "cwd": "."}],
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
            json.dumps(
                {
                    "action": "finalize",
                    "feedback": "",
                    "reason": "accept failure",
                }
            ),
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


def test_readonly_refuses_done_until_report_section(tmp_path: Path):
    """Readonly skips cannot satisfy report_section; DECLARE_DONE waits for OBSERVE."""
    from MaintainAll.graph.nodes import make_nodes

    mission = Mission(
        id="ro-summary",
        name="Readonly summary",
        description="d",
        skills=[],
        schedule=None,
        notify=NotifyConfig(),
        allowed_commands=[AllowedCommand(pattern=r"^bash -n\b", cwd=".")],
        tasks=[
            TaskNode(
                id="main",
                name="Syntax check",
                needs=[],
                instruction="Summarize bash -n results under ## summary",
                expect=Expect(type="report_section", name="summary"),
                script="bash -n missing.sh",
            )
        ],
    )
    llm = FakeLLM(
        [
            "REACT:DECLARE_DONE",
            "REACT:OBSERVE:## summary\nreadonly：命令未执行，仅记录跳过。\n",
        ]
    )
    events: list[dict] = []

    def on_event(ev: dict) -> None:
        events.append(ev)

    nodes = make_nodes(llm=llm, event_callback=on_event, max_iters=8)
    out = nodes["react_loop"](
        {
            "user_input": "check maintaince scripts",
            "mode": "readonly",
            "repo_path": str(tmp_path),
            "mission_draft": mission_to_dict(mission),
            "observations": [],
            "report_draft": "",
            "event_log": [],
            "report_language": "zh-CN",
            "validation_errors": [],
        }
    )
    assert out.get("react_done") is True
    assert "## summary" in (out.get("report_draft") or "")
    assert any(e.get("type") == "cmd_skipped" for e in events)
    assert any(e.get("type") == "react_nudge" for e in events)
    # Prompt must surface required/missing sections to the model
    assert any(
        "Required report sections:" in (m.get("content") or "")
        for call in llm.calls
        for m in call
        if m.get("role") == "user"
    )

    validated = nodes["validate"](
        {
            **out,
            "mode": "readonly",
            "repo_path": str(tmp_path),
            "mission_draft": out.get("mission_draft") or mission_to_dict(mission),
        }
    )
    assert validated.get("validation_ok") is True


def test_missing_report_sections_helper():
    from MaintainAll.graph.nodes import (
        _missing_report_sections,
        _required_report_section_names,
    )

    mission = Mission(
        id="m",
        name="M",
        description="d",
        skills=[],
        schedule=None,
        notify=NotifyConfig(),
        allowed_commands=[],
        tasks=[
            TaskNode(
                id="a",
                name="A",
                needs=[],
                instruction="i",
                expect=Expect(type="report_section", name="summary"),
            ),
            TaskNode(
                id="b",
                name="B",
                needs=["a"],
                instruction="i",
                expect=Expect(type="report_section", name="summary"),
            ),
            TaskNode(
                id="c",
                name="C",
                needs=["b"],
                instruction="i",
                expect=Expect(type="contains", patterns=["x"]),
            ),
        ],
    )
    assert _required_report_section_names(mission) == ["summary"]
    assert _missing_report_sections(mission, "") == ["summary"]
    assert _missing_report_sections(mission, "## Summary\n") == ["summary"]
    assert _missing_report_sections(mission, "## summary\nok\n") == []
