from MaintainAll.browser_open import browser_open_safe, remote_browser_helper, try_open_url


def test_remote_cursor_browser_is_not_safe(monkeypatch):
    monkeypatch.setenv(
        "BROWSER",
        "/home/x/.cursor-server/bin/linux-x64/hash/bin/helpers/browser.sh",
    )
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert remote_browser_helper() is True
    assert browser_open_safe() is False
    assert try_open_url("https://example.com") is False


def test_gui_display_without_remote_helper_is_safe(monkeypatch):
    monkeypatch.delenv("BROWSER", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    assert remote_browser_helper() is False
    assert browser_open_safe() is True
