from __future__ import annotations

import threading
from time import monotonic

from MaintainAll.config import Settings
from MaintainAll.graph.workflow import run_session
from MaintainAll.memory.session import SessionMemory
from MaintainAll.tui.cancel import SessionCancelArm


def test_session_cancel_arm_first_press_arms_second_confirms():
    arm = SessionCancelArm(window_s=2.0)
    t0 = 1000.0
    assert arm.press(now=t0) == "armed"
    assert arm.press(now=t0 + 0.5) == "confirm"
    # After confirm, next press arms again
    assert arm.press(now=t0 + 0.6) == "armed"


def test_session_cancel_arm_expires():
    arm = SessionCancelArm(window_s=2.0)
    t0 = 1000.0
    assert arm.press(now=t0) == "armed"
    assert arm.press(now=t0 + 2.5) == "armed"  # expired → re-arm, not confirm


def test_run_session_stops_when_cancel_event_set(tmp_path):
    """Soft cancel: after a node finishes, cancel_event stops further work."""
    cancel = threading.Event()
    events: list[dict] = []

    def assess_fn(state):
        cancel.set()
        return {
            "feasible": True,
            "reason": "ok",
            "event_log": list(state.get("event_log") or [])
            + [{"type": "assess", "feasible": True, "reason": "ok"}],
        }

    settings = Settings(repo_path=str(tmp_path), agent_mode="readonly")
    memory = SessionMemory(mode="readonly")
    result = run_session(
        "do something",
        settings=settings,
        memory=memory,
        assess_fn=assess_fn,
        event_callback=events.append,
        cancel_event=cancel,
        skip_review=True,
    )

    assert result.get("cancelled") is True
    assert any(e.get("type") == "session_cancelled" for e in events)
    # Should not have finalized a report after cancel mid-flight
    assert not result.get("report_path")
