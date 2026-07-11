from __future__ import annotations

from typing import Any, Literal, TypedDict


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
    observations: list[str]
    report_draft: str
    report_path: str
    report_language: str
    log_path: str
    messages: list[dict[str, str]]
    interrupt: str | None
    cancelled: bool
    repo_path: str
    data_dir: str
    mail_notified: bool
    event_log: list[dict[str, Any]]
