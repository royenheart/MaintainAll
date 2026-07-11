from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from MaintainAll.config import Settings
from MaintainAll.graph.nodes import make_nodes, mission_from_dict, mission_to_dict
from MaintainAll.graph.state import AgentState
from MaintainAll.memory.session import SessionMemory
from MaintainAll.memory.session_log import SessionLog
from MaintainAll.missions.models import Mission

MAX_VALIDATE_ATTEMPTS = 2
MAX_REVISE_ATTEMPTS = 1


def route_after_assess(state: AgentState | dict[str, Any]) -> str:
    if state.get("feasible") is False:
        return "reject"
    return "build_board"


def route_after_review(state: AgentState | dict[str, Any]) -> str:
    action = state.get("review_action")
    # Waiting for TUI / no action yet — stop the graph
    if action is None or state.get("interrupt") == "review":
        return "end"
    if action == "reject":
        return "end"
    if action == "feedback":
        return "build_board"
    if action == "approve":
        return "react_loop"
    return "end"


def route_after_react(state: AgentState | dict[str, Any]) -> str:
    if state.get("rebuild_board"):
        return "build_board"
    return "validate"


def route_after_validate(state: AgentState | dict[str, Any]) -> str:
    if state.get("validation_ok"):
        return "finalize"
    errors = state.get("validation_errors") or []
    validate_attempts = sum(
        1 for event in (state.get("event_log") or []) if event.get("type") == "validate"
    )
    revise_attempts = sum(
        1 for event in (state.get("event_log") or []) if event.get("type") == "revise_mission"
    )
    if any(str(err).startswith("HARD:") for err in errors):
        return "finalize"
    if validate_attempts < MAX_VALIDATE_ATTEMPTS:
        return "react_loop"
    if revise_attempts < MAX_REVISE_ATTEMPTS:
        return "revise_mission"
    return "finalize"


def route_after_revise(state: AgentState | dict[str, Any]) -> str:
    if state.get("rebuild_board"):
        return "build_board"
    return "finalize"


def build_graph(
    llm: Any = None,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    *,
    assess_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    max_iters: int = 10,
    settings: Settings | None = None,
):
    nodes = make_nodes(
        llm=llm,
        event_callback=event_callback,
        assess_fn=assess_fn,
        max_iters=max_iters,
        settings=settings,
    )
    graph = StateGraph(AgentState)
    graph.add_node("assess", nodes["assess"])
    graph.add_node("build_board", nodes["build_board"])
    graph.add_node("review", nodes["review"])
    graph.add_node("react_loop", nodes["react_loop"])
    graph.add_node("validate", nodes["validate"])
    graph.add_node("revise_mission", nodes["revise_mission"])
    graph.add_node("finalize", nodes["finalize"])
    graph.add_node("reject", nodes["reject"])

    graph.add_edge(START, "assess")
    graph.add_conditional_edges(
        "assess",
        route_after_assess,
        {"reject": "reject", "build_board": "build_board"},
    )
    graph.add_edge("build_board", "review")
    graph.add_conditional_edges(
        "review",
        route_after_review,
        {
            "end": END,
            "build_board": "build_board",
            "react_loop": "react_loop",
        },
    )
    graph.add_conditional_edges(
        "react_loop",
        route_after_react,
        {"build_board": "build_board", "validate": "validate"},
    )
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "react_loop": "react_loop",
            "revise_mission": "revise_mission",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "revise_mission",
        route_after_revise,
        {
            "build_board": "build_board",
            "finalize": "finalize",
        },
    )
    graph.add_edge("finalize", END)
    graph.add_edge("reject", END)
    return graph.compile()


def _initial_state(
    user_input: str,
    *,
    settings: Settings,
    memory: SessionMemory | None = None,
    mode: str | None = None,
    skip_review: bool = False,
    mission_draft: dict[str, Any] | None = None,
    feasible: bool | None = None,
) -> AgentState:
    resolved_mode = mode or (memory.mode if memory else None) or settings.agent_mode
    state: AgentState = {
        "user_input": user_input,
        "mode": resolved_mode,  # type: ignore[typeddict-item]
        "skip_review": skip_review,
        "repo_path": settings.repo_path,
        "data_dir": settings.data_dir,
        "report_language": settings.report_language or "zh-CN",
        "messages": list(memory.messages) if memory else [],
        "observations": [],
        "report_draft": "",
        "event_log": [],
        "rebuild_board": False,
        "react_done": False,
        "validation_ok": None,
        "validation_errors": [],
        "interrupt": None,
        "review_action": None,
        "review_feedback": "",
    }
    if mission_draft is not None:
        state["mission_draft"] = mission_draft
    if feasible is not None:
        state["feasible"] = feasible
    return state


def _sync_memory_from_result(memory: SessionMemory | None, result: dict[str, Any]) -> None:
    if memory is None:
        return
    if result.get("report_path"):
        memory.last_report = Path(result["report_path"])
    if result.get("mission_draft"):
        try:
            memory.mission = mission_from_dict(
                {
                    k: v
                    for k, v in result["mission_draft"].items()
                    if not str(k).startswith("_")
                }
            )
        except Exception:
            pass
    if result.get("reject_reason"):
        memory.assess_notes = str(result["reject_reason"])


def _finish_session(
    result: dict[str, Any],
    *,
    session_log: SessionLog,
    memory: SessionMemory | None,
    chained_event_callback: Callable[[dict[str, Any]], None],
    cancelled: bool = False,
) -> AgentState:
    out = dict(result)
    if cancelled:
        out["interrupt"] = None
        out["cancelled"] = True
        if not (out.get("reject_reason") or "").strip():
            out["reject_reason"] = "Cancelled by user"
        chained_event_callback({"type": "session_cancelled"})
    elif out.get("interrupt") == "review":
        # Review was already handled by the outer loop; do not leak it.
        out["interrupt"] = None
    # else: keep interrupt (notably finalize → "solidify") for the TUI.
    _sync_memory_from_result(memory, out)
    out["log_path"] = str(session_log.path)
    session_log.write({"type": "session_end", "result_keys": sorted(out.keys())})
    return out  # type: ignore[return-value]


def _stream_until_interrupt_or_end(
    app: Any,
    state: dict[str, Any],
    *,
    cancel_event: threading.Event | None,
) -> tuple[dict[str, Any], bool]:
    """Run graph via stream so cancel can stop between nodes. Returns (state, cancelled)."""
    result = state
    if cancel_event is not None and cancel_event.is_set():
        return result, True
    for values in app.stream(state, stream_mode="values"):
        result = dict(values)
        if cancel_event is not None and cancel_event.is_set():
            return result, True
    return result, False


def run_session(
    user_input: str,
    *,
    settings: Settings,
    memory: SessionMemory,
    review_callback: Callable[[AgentState], dict[str, Any]] | None = None,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    llm: Any = None,
    assess_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    mission_draft: dict[str, Any] | None = None,
    mode: str | None = None,
    skip_review: bool = False,
    feasible: bool | None = None,
    cancel_event: threading.Event | None = None,
) -> AgentState:
    session_log = SessionLog(Path(settings.repo_path), data_dir=settings.data_dir)
    session_log.write({"type": "user_input", "text": user_input})

    def chained_event_callback(event: dict[str, Any]) -> None:
        session_log.write(event)
        if event_callback is not None:
            event_callback(event)

    app = build_graph(
        llm=llm,
        event_callback=chained_event_callback,
        assess_fn=assess_fn,
        settings=settings,
    )
    state: dict[str, Any] = dict(
        _initial_state(
            user_input,
            settings=settings,
            memory=memory,
            mode=mode,
            skip_review=skip_review,
            mission_draft=mission_draft,
            feasible=feasible,
        )
    )
    memory.add_message("user", user_input)

    while True:
        result, cancelled = _stream_until_interrupt_or_end(
            app, state, cancel_event=cancel_event
        )
        if cancelled:
            return _finish_session(
                result,
                session_log=session_log,
                memory=memory,
                chained_event_callback=chained_event_callback,
                cancelled=True,
            )
        if result.get("interrupt") == "review" and review_callback is not None:
            if cancel_event is not None and cancel_event.is_set():
                return _finish_session(
                    result,
                    session_log=session_log,
                    memory=memory,
                    chained_event_callback=chained_event_callback,
                    cancelled=True,
                )
            decision = review_callback(result)  # type: ignore[arg-type]
            if cancel_event is not None and cancel_event.is_set():
                return _finish_session(
                    {**result, "review_action": decision.get("action"), "review_feedback": decision.get("feedback", "")},
                    session_log=session_log,
                    memory=memory,
                    chained_event_callback=chained_event_callback,
                    cancelled=True,
                )
            action = decision.get("action")
            feedback = decision.get("feedback", "")
            if action == "reject":
                reason = (feedback or "").strip() or "User rejected mission board"
                chained_event_callback({"type": "review", "action": "reject", "auto": False})
                chained_event_callback({"type": "reject", "reason": reason})
                return _finish_session(
                    {
                        **result,
                        "review_action": "reject",
                        "review_feedback": feedback,
                        "reject_reason": reason,
                    },
                    session_log=session_log,
                    memory=memory,
                    chained_event_callback=chained_event_callback,
                )
            state = {
                **result,
                "review_action": action,
                "review_feedback": feedback,
                "interrupt": None,
            }
            continue
        return _finish_session(
            result,
            session_log=session_log,
            memory=memory,
            chained_event_callback=chained_event_callback,
        )


def run_mission(
    mission: Mission,
    *,
    settings: Settings,
    skip_review: bool = True,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    llm: Any = None,
    assess_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> AgentState:
    app = build_graph(
        llm=llm,
        event_callback=event_callback,
        assess_fn=assess_fn,
        settings=settings,
    )
    draft = mission_to_dict(mission)
    state = _initial_state(
        user_input=f"run mission {mission.id}",
        settings=settings,
        mode="mission",
        skip_review=skip_review,
        mission_draft=draft,
        feasible=True,
    )
    return app.invoke(state)  # type: ignore[return-value]
