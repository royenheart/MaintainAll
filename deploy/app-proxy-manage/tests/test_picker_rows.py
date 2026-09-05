from __future__ import annotations

from win_apps import AppEntry
from tray import picker_rows


def _e(exe: str, name: str = "", *, supported: bool = True, path: str = "") -> AppEntry:
    return AppEntry(exe=exe, name=name or exe, path=path, source="test", supported=supported)


def test_checked_items_sort_first():
    rows = picker_rows(
        [_e("chrome.exe", "Chrome"), _e("cursor.exe", "Cursor"), _e("ssh.exe", "OpenSSH")],
        {"cursor.exe"},
        "",
        "all",
    )
    keys = [r.key for r in rows]
    assert keys[0] == "cursor.exe"
    assert "chrome.exe" in keys


def test_filter_checked_and_unchecked():
    entries = [_e("a.exe", "Alpha"), _e("b.exe", "Beta"), _e("c.exe", "Gamma", supported=False)]
    selected = {"a.exe"}
    checked = picker_rows(entries, selected, "", "checked")
    assert [r.key for r in checked] == ["a.exe"]
    unchecked = picker_rows(entries, selected, "", "unchecked")
    assert [r.key for r in unchecked] == ["b.exe"]


def test_search_matches_name_exe_path_and_keeps_ghosts():
    entries = [_e("chrome.exe", "Google Chrome", path=r"C:\Program Files\Chrome\chrome.exe")]
    rows = picker_rows(entries, {"saved.exe", "chrome.exe"}, "chrome", "all")
    keys = [r.key for r in rows]
    assert keys[0] == "chrome.exe"
    ghost = picker_rows(entries, {"ghost.exe"}, "ghost", "all")
    assert [r.key for r in ghost] == ["ghost.exe"]
    assert picker_rows(entries, set(), "firefox", "all") == []
