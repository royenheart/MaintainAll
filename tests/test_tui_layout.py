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


def test_imports():
    assert MaintainAllApp is not None
    assert RunStatePane is not None
    assert DetailModal is not None
    assert ReviewModal is not None
    assert SettingsModal is not None
    assert SolidifyModal is not None


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