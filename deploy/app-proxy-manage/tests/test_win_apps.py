from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.mark.skipif(os.name != "nt", reason="Windows-only enumerator")
def test_scan_apps_finds_win32_exe():
    from win_apps import _read_shortcuts, scan_apps

    shortcuts = _read_shortcuts()
    assert shortcuts, "应能解析开始菜单 .lnk"
    apps = scan_apps()
    supported = [a for a in apps if a.supported and a.exe]
    assert supported, "应至少扫到一个开始菜单或窗口应用"
    assert all(a.exe.lower().endswith(".exe") for a in supported)
    keys = {a.exe.lower() for a in supported}
    assert "explorer.exe" not in keys
    assert any(a.source == "shortcut" for a in supported)


@pytest.mark.skipif(os.name != "nt", reason="Windows-only enumerator")
def test_scan_apps_includes_openssh_if_present():
    from win_apps import _system_component_entries, scan_apps

    ssh = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "OpenSSH" / "ssh.exe"
    if not ssh.is_file():
        pytest.skip("本机没有 System32\\OpenSSH\\ssh.exe")
    components = _system_component_entries()
    assert any(a.exe.lower() == "ssh.exe" and a.source == "component" for a in components)
    apps = scan_apps()
    hit = next(a for a in apps if a.supported and a.exe.lower() == "ssh.exe")
    assert "OpenSSH" in hit.name
    assert hit.source in {"component", "path", "apppath"}


@pytest.mark.skipif(os.name != "nt", reason="Windows-only enumerator")
def test_scan_running_includes_current_python():
    from win_apps import scan_running

    running = scan_running()
    keys = {a.exe.lower() for a in running if a.supported}
    assert any(k.startswith("python") for k in keys) or "py.exe" in keys or keys
