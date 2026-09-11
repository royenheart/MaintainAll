"""Layer 1: Deterministic operations tests (platform-aware)."""

import os

import pytest

from cua_control_plane import deterministic_ops as dops


class TestPlatformDetection:
    def test_is_windows(self):
        assert dops._is_windows() == (os.name == "nt")

    def test_is_linux(self):
        assert dops._is_linux() == (os.name == "posix" and os.uname().sysname != "Darwin")

    def test_platform_name(self):
        name = dops._platform_name()
        assert name in ("windows", "linux", "macos")


class TestToolDetection:
    def test_check_tool_positive(self):
        assert dops._check_tool("python") or dops._check_tool("python3")

    def test_check_tool_negative(self):
        assert not dops._check_tool("nonexistent_tool_xyz_123")


class TestListApps:
    def test_list_apps_returns_list(self):
        result = dops.list_apps()
        assert isinstance(result, list)

    def test_list_apps_items_have_required_keys(self):
        result = dops.list_apps()
        for item in result:
            assert "name" in item
            assert "window_title" in item
            assert "platform" in item


class TestAppInfo:
    def test_app_info_nonexistent(self):
        result = dops.app_info("completely_nonexistent_app_xyz_12345")
        # Should return None for unknown app (not crash)
        assert result is None or isinstance(result, dict)

    def test_app_info_structure(self):
        result = dops.app_info("python")  # may or may not exist
        if result is not None:
            assert "name" in result
            assert "platform" in result
            assert "window_rect" in result


class TestListInstalledApps:
    def test_list_installed_apps_returns_list(self):
        result = dops.list_installed_apps()
        assert isinstance(result, list)

    def test_list_installed_apps_structure(self):
        result = dops.list_installed_apps()
        for item in result:
            assert "name" in item
            assert "path" in item


class TestDesktopFileParsing:
    @pytest.mark.skipif(not dops._is_linux(), reason="Linux-only test")
    def test_desktop_file_for_firefox(self):
        df = dops._linux_desktop_file_for("firefox")
        if df:
            info = dops._linux_desktop_app_info(df)
            assert info is not None
            assert "name" in info
            assert "exe_path" in info

    @pytest.mark.skipif(not dops._is_linux(), reason="Linux-only test")
    def test_desktop_file_parsing(self):
        """Parse a known .desktop file."""
        from pathlib import Path
        test_file = Path("/usr/share/applications/firefox.desktop")
        if test_file.exists():
            info = dops._linux_desktop_app_info(test_file)
            assert info is not None
            assert info["name"]  # Should have a name


class TestWmctrlParsing:
    def test_parse_wmctrl_line_valid(self):
        line = "0x02e00001  0  hostname  Firefox - Test Page"
        parsed = dops._parse_wmctrl_line(line)
        assert parsed is not None
        assert parsed["window_id"] == "0x02e00001"
        assert parsed["desktop"] == 0
        assert parsed["window_title"] == "Firefox - Test Page"

    def test_parse_wmctrl_line_invalid(self):
        assert dops._parse_wmctrl_line("") is None
        assert dops._parse_wmctrl_line("short") is None
