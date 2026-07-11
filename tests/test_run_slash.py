from __future__ import annotations

import asyncio
from pathlib import Path

from MaintainAll.memory.prompt_history import append_prompt_history, load_prompt_history
from MaintainAll.missions.models import Expect, Mission, NotifyConfig, TaskNode
from MaintainAll.missions.resolve import (
    format_mission_candidate,
    is_run_command_prefix,
    parse_run_command,
    resolve_mission,
)
from MaintainAll.tui.panes import (
    ChatSlashSuggester,
    PromptHistory,
    run_completion_items,
    slash_completion_options,
)


def _mission(mid: str, name: str | None = None) -> Mission:
    return Mission(
        id=mid,
        name=name or mid,
        description="d",
        skills=[],
        schedule=None,
        notify=NotifyConfig(),
        allowed_commands=[],
        tasks=[
            TaskNode(
                id="t1",
                name="T",
                needs=[],
                instruction="i",
                expect=Expect(type="contains", patterns=["ok"]),
            )
        ],
    )


def test_parse_run_command():
    assert parse_run_command("/run") == ""
    assert parse_run_command("/run daed-connectivity-check") == "daed-connectivity-check"
    assert parse_run_command("/solidify") is None


def test_is_run_command_prefix():
    assert is_run_command_prefix("/r")
    assert is_run_command_prefix("/run foo")
    assert not is_run_command_prefix("/solidify")


def test_resolve_mission_by_name_prefix():
    missions = [
        _mission("daed-connectivity-check", name="Daed Connectivity"),
        _mission("daed-other", name="Other Daed"),
        _mission("modulefiles-list", name="List modules"),
    ]
    m, _ = resolve_mission("List", missions)
    assert m is not None and m.id == "modulefiles-list"
    m, cands = resolve_mission("Daed", missions)
    assert m is None
    assert {x.id for x in cands} == {"daed-connectivity-check", "daed-other"}


def test_run_completion_items():
    missions = [
        _mission("zebra", name="Z"),
        _mission("alpha", name="A Mission"),
    ]
    items = run_completion_items("", missions)
    assert [i.value for i in items] == ["/run alpha", "/run zebra"]
    assert "A Mission" in items[0].label

    items = run_completion_items("A Mis", missions)
    assert len(items) == 1
    assert items[0].value == "/run alpha"


def test_slash_completion_options_no_mission_ids():
    opts = slash_completion_options([_mission("alpha")])
    assert opts == ["/run ", "/solidify"]


def test_chat_slash_suggester_does_not_pick_first_mission():
    missions = [_mission("modulefiles-list", name="List modules")]
    options = slash_completion_options(missions)
    suggester = ChatSlashSuggester(lambda: options, get_missions=lambda: missions)

    async def _check() -> None:
        assert await suggester.get_suggestion("/run ") is None
        assert await suggester.get_suggestion("/r") == "/run "
        assert await suggester.get_suggestion("/sol") == "/solidify"

    asyncio.run(_check())


def test_prompt_history_persists_per_path(tmp_path: Path):
    path_a = tmp_path / "A" / "prompt.jsonl"
    path_b = tmp_path / "B" / "prompt.jsonl"
    append_prompt_history(path_a, "from-a")
    append_prompt_history(path_b, "from-b")
    assert load_prompt_history(path_a) == ["from-a"]
    assert load_prompt_history(path_b) == ["from-b"]

    hist = PromptHistory(on_push=lambda t: append_prompt_history(path_a, t))
    hist.load(load_prompt_history(path_a))
    hist.push("second")
    assert load_prompt_history(path_a) == ["from-a", "second"]
