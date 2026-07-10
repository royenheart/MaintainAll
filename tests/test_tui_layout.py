"""Non-interactive smoke for AI-mode TUI composition."""

import pytest

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
