"""Non-interactive smoke for AI-mode TUI composition."""

from pydantic import SecretStr
import pytest

from MaintainAll.config import Settings
from MaintainAll.memory.session import SessionMemory
from MaintainAll.tui.app import MaintainAllApp
from MaintainAll.tui.modals import DetailModal, ReviewModal, SettingsModal, SolidifyModal
from MaintainAll.tui.panes import ChatStream, IdleSidebar, RunStatePane


@pytest.mark.asyncio
async def test_app_composes_without_run():
    app = MaintainAllApp()
    assert app.TITLE == "MaintainAll"
    async with app.run_test(size=(120, 40)) as pilot:
        assert pilot.app.query_one("#chat-stream", ChatStream)
        assert pilot.app.query_one("#chat-input")
        assert pilot.app.query_one("#sidebar")
        assert pilot.app.query_one("#mode-banner")
        assert pilot.app.query_one("#idle-sidebar", IdleSidebar)


def test_detail_and_review_share_mission_board_with_script_collapsible():
    from MaintainAll.graph.nodes import mission_to_dict
    from MaintainAll.missions.models import (
        AllowedCommand,
        Expect,
        Mission,
        NotifyConfig,
        TaskNode,
    )
    from MaintainAll.tui.modals import DetailModal, ReviewModal, compose_mission_board
    from textual.app import App, ComposeResult
    from textual.widgets import Collapsible, Static

    mission = Mission(
        id="demo-detail",
        name="Demo Detail",
        description="show tasks",
        skills=[],
        schedule=None,
        notify=NotifyConfig(),
        allowed_commands=[AllowedCommand(pattern=r"^echo hello$")],
        tasks=[
            TaskNode(
                id="t1",
                name="First",
                needs=[],
                instruction="do it",
                expect=Expect(type="report_section", name="summary"),
                script="echo hello",
            )
        ],
    )
    draft = mission_to_dict(mission, include_status=False)

    class _Probe(App):
        def compose(self) -> ComposeResult:
            yield from compose_mission_board(draft)

        def on_mount(self) -> None:
            assert len(self.query(Collapsible)) >= 1
            code = self.query_one(".script-code", Static)
            assert "echo hello" in code._content  # type: ignore[attr-defined]
            texts = [str(s._content) for s in self.query(Static)]  # type: ignore[attr-defined]
            assert any("Tasks:" in t for t in texts)
            assert any("[t1] First" in t for t in texts)
            self.exit()

    _Probe().run()

    # Both modals call the same compose_mission_board helper.
    import inspect

    assert "compose_mission_board" in inspect.getsource(DetailModal._compose_body)
    assert "compose_mission_board" in inspect.getsource(ReviewModal.compose)


def test_settings_secret_mask_and_report_language_options():
    from pydantic import SecretStr

    from MaintainAll.config import Settings
    from MaintainAll.tui.modals import SettingsModal

    empty = SettingsModal(Settings())
    assert empty._secret_field_value(None) == ""
    assert empty._pending_secret("") == ""
    assert empty._pending_secret("***") == ""
    assert empty._pending_secret("sk-new") == "sk-new"

    filled = SettingsModal(Settings(api_key=SecretStr("sk-secret")))
    assert filled._secret_field_value(filled.settings.api_key) == "***"

    langs = {value for _label, value in SettingsModal.REPORT_LANGUAGE_OPTIONS}
    assert "zh-CN" in langs and "en" in langs
    assert filled._report_language_value() == "zh-CN"


def test_session_llm_from_settings_none_without_key():
    assert MaintainAllApp._session_llm_from_settings(Settings()) is None


def test_session_llm_from_settings_builds(monkeypatch):
    monkeypatch.setattr(
        "MaintainAll.tui.app.build_chat_model", lambda settings: "FAKE_LLM"
    )
    settings = Settings(api_key=SecretStr("sk-test"))
    assert MaintainAllApp._session_llm_from_settings(settings) == "FAKE_LLM"


def test_invoke_agent_session_passes_llm(monkeypatch, tmp_path):
    captured: dict = {}

    def fake_run_session(*args, **kwargs):
        captured.update(kwargs)
        return {"report_path": None}

    monkeypatch.setattr("MaintainAll.tui.app.run_session", fake_run_session)
    monkeypatch.setattr(
        "MaintainAll.tui.app.build_chat_model", lambda settings: "FAKE_LLM"
    )

    app = MaintainAllApp()
    app.settings = Settings(api_key=SecretStr("sk-test"), repo_path=str(tmp_path))
    app.memory = SessionMemory(mode="restricted")
    app._invoke_agent_session(
        "hello",
        event_callback=lambda e: None,
        review_callback=lambda s: {"action": "approve", "feedback": ""},
    )
    assert captured.get("llm") == "FAKE_LLM"