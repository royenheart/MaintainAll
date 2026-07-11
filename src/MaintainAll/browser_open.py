"""Safe browser opening (avoid Cursor/VS Code remote BROWSER helpers)."""

from __future__ import annotations

import os
import webbrowser


def remote_browser_helper() -> bool:
    """True when $BROWSER points at Cursor/VS Code remote pipe helpers."""
    browser = (os.environ.get("BROWSER") or "").lower()
    markers = ("cursor-server", "vscode-server", ".vscode-server", "code-server")
    return any(m in browser for m in markers)


def gui_display_available() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def browser_open_safe() -> bool:
    """Whether webbrowser.open is likely to work without remote-pipe errors."""
    if remote_browser_helper():
        return False
    if gui_display_available():
        return True
    return False


def try_open_url(url: str) -> bool:
    """Open *url* in a browser only when safe; never raise."""
    if not browser_open_safe():
        return False
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False
