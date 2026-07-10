from MaintainAll.graph.workflow import (
    route_after_assess,
    route_after_react,
    route_after_review,
    route_after_validate,
)


def test_route_after_assess_reject():
    assert route_after_assess({"feasible": False}) == "reject"


def test_route_after_assess_build_board():
    assert route_after_assess({"feasible": True}) == "build_board"
    assert route_after_assess({"feasible": None}) == "build_board"
    assert route_after_assess({}) == "build_board"


def test_route_after_review_reject():
    assert route_after_review({"review_action": "reject"}) == "end"


def test_route_after_review_feedback():
    assert route_after_review({"review_action": "feedback"}) == "build_board"


def test_route_after_review_approve():
    assert route_after_review({"review_action": "approve"}) == "react_loop"


def test_route_after_review_waiting_for_tui():
    assert route_after_review({"interrupt": "review"}) == "end"
    assert route_after_review({"interrupt": "review", "review_action": None}) == "end"
    assert route_after_review({}) == "end"


def test_route_after_react_rebuild():
    assert route_after_react({"rebuild_board": True, "react_done": True}) == "build_board"


def test_route_after_react_validate():
    assert route_after_react({"rebuild_board": False, "react_done": True}) == "validate"
    assert route_after_react({"react_done": True}) == "validate"
    assert route_after_react({}) == "validate"


def test_route_after_validate_ok():
    assert route_after_validate({"validation_ok": True}) == "finalize"


def test_route_after_validate_retry():
    state = {
        "validation_ok": False,
        "validation_errors": ["t1: missing"],
        "event_log": [{"type": "validate", "ok": False}],
    }
    assert route_after_validate(state) == "react_loop"


def test_route_after_validate_hard_fail():
    state = {
        "validation_ok": False,
        "validation_errors": ["HARD: missing mission_draft"],
        "event_log": [{"type": "validate"}],
    }
    assert route_after_validate(state) == "finalize"


def test_route_after_validate_exhausted_retries():
    state = {
        "validation_ok": False,
        "validation_errors": ["t1: missing"],
        "event_log": [
            {"type": "validate", "ok": False},
            {"type": "validate", "ok": False},
        ],
    }
    assert route_after_validate(state) == "finalize"
