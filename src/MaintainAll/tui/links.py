"""Open or present external URLs safely (including headless / remote TUI)."""

from __future__ import annotations

from MaintainAll.browser_open import (
    browser_open_safe,
    gui_display_available,
    remote_browser_helper,
    try_open_url,
)

__all__ = [
    "browser_open_safe",
    "gui_display_available",
    "remote_browser_helper",
    "try_open_url",
]
