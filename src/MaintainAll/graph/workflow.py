from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from MaintainAll.config import Settings
from MaintainAll.graph.nodes import make_nodes, mission_from_dict, mission_to_dict
from MaintainAll.graph.state import AgentState
from MaintainAll.memory.session import SessionMemory
from MaintainAll.missions.models import Mission

MAX_VALIDATE_ATTEMPTS = 2


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
    if any(str(err).startswith("HARD:") for err in errors):
        return "end"
    attempts = sum(
        1 for event in (state.get("event_log") or []) if event.get("type") == "validate"
    )
    if attempts < MAX_VALIDATE_ATTEMPTS:
        return "react_loop"
    return "end"


def build_graph(
    llm: Any = None,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    *,
    assess_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    max_iters: int = 10,
):
    nodes = make_nodes(
        llm=llm,
        event_callback=event_callback,
        assess_fn=assess_fn,
        max_iters=max_iters,
    )
    graph = StateGraph(AgentState)
    graph.add_node("assess", nodes["assess"])
    graph.add_node("build_board", nodes["build_board"])
    graph.add_node("review", nodes["review"])
    graph.add_node("react_loop", nodes["react_loop"])
    graph.add_node("validate", nodes["validate"])
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
            "finalize": "finalize",
            "end": END,
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
        "messages": list(memory.messages) if memory else [],
        "observations": [],
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


def run_session(
    user_input: str,
    *,
    settings: Settings,
    memory: SessionMemory,
    review_callback: Callable[[AgentState], dict[str, Any]] | None = None,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    llm: Any = None,
    assess_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> AgentState:
    app = build_graph(llm=llm, event_callback=event_callback, assess_fn=assess_fn)
    state: dict[str, Any] = dict(
        _initial_state(
            user_input,
            settings=settings,
            memory=memory,
            skip_review=False,
        )
    )
    memory.add_message("user", user_input)

    while True:
        result = app.invoke(state)
        if result.get("interrupt") == "review" and review_callback is not None:
            decision = review_callback(result)  # type: ignore[arg-type]
            state = {
                **result,
                "review_action": decision.get("action"),
                "review_feedback": decision.get("feedback", ""),
                "interrupt": None,
            }
            continue
        if memory is not None:
            if result.get("report_path"):
                from pathlib import Path

                memory.last_report = Path(result["report_path"])
            if result.get("mission_draft"):
                try:
                    memory.mission = mission_from_dict(
                        {k: v for k, v in result["mission_draft"].items() if not str(k).startswith("_")}
                    )
                except Exception:
                    pass
            if result.get("reject_reason"):
                memory.assess_notes = str(result["reject_reason"])
        return result  # type: ignore[return-value]


def run_mission(
    mission: Mission,
    *,
    settings: Settings,
    skip_review: bool = True,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
    llm: Any = None,
    assess_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> AgentState:
    app = build_graph(llm=llm, event_callback=event_callback, assess_fn=assess_fn)
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
