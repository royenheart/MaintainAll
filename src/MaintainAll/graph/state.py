from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


class AgentState(TypedDict, total=False):
    user_input: str
    mode: Literal["readonly", "restricted", "unlimited", "mission"]
    skip_review: bool
    feasible: bool | None
    reject_reason: str
    mission_draft: dict[str, Any]
    review_action: Literal["approve", "reject", "feedback"] | None
    review_feedback: str
    rebuild_board: bool
    react_done: bool
    validation_ok: bool | None
    validation_errors: list[str]
    observations: Annotated[list[str], operator.add]
    report_draft: str
    report_path: str
    messages: list[dict[str, str]]
    interrupt: str | None
    repo_path: str
    event_log: list[dict[str, Any]]
