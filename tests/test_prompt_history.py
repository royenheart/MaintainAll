from __future__ import annotations

from MaintainAll.tui.panes import PromptHistory


def test_prompt_history_older_newer_and_draft():
    hist = PromptHistory()
    hist.push("one")
    hist.push("two")
    hist.push("three")

    assert hist.older("draft") == "three"
    assert hist.older("three") == "two"
    assert hist.older("two") == "one"
    assert hist.older("one") is None  # already oldest

    assert hist.newer("one") == "two"
    assert hist.newer("two") == "three"
    assert hist.newer("three") == "draft"
    assert hist.newer("draft") is None


def test_prompt_history_skips_blank_and_consecutive_dupes():
    hist = PromptHistory()
    hist.push("")
    hist.push("  ")
    hist.push("same")
    hist.push("same")
    hist.push("other")
    assert hist.entries == ["same", "other"]


def test_prompt_history_max_size():
    hist = PromptHistory(max_size=2)
    hist.push("a")
    hist.push("b")
    hist.push("c")
    assert hist.entries == ["b", "c"]
