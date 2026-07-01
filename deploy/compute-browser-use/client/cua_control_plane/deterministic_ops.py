"""Deterministic desktop operations — Windows and Linux support.

These operations avoid screenshot-based CUA workflows by directly querying
the OS for app information, window positions, and process management.

Platform support:
  - Windows: PowerShell + Win32 API
  - Linux:   wmctrl + xdotool + .desktop files (X11/Wayland via XWayland)
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Suppress the console window that Windows allocates for each child process
# when the parent has no console (pythonw.exe). 0 on POSIX.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def _is_windows() -> bool:
    return os.name == "nt"


def _is_linux() -> bool:
    return os.name == "posix" and not _is_macos()


def _is_macos() -> bool:
    return os.uname().sysname == "Darwin"


def _platform_name() -> str:
    if _is_windows():
        return "windows"
    if _is_macos():
        return "macos"
    return "linux"


# ---------------------------------------------------------------------------
# Tool availability checks
# ---------------------------------------------------------------------------

def _check_tool(name: str) -> bool:
    """Check if a CLI tool is available on PATH."""
    return shutil.which(name) is not None


def _require_tool(name: str, hint: str = "") -> None:
    """Raise RuntimeError if a required tool is not available."""
    if not _check_tool(name):
        msg = (
            f"Required tool '{name}' not found. "
            f"Install it with your package manager"
        )
        if hint:
            msg += f": {hint}"
        raise RuntimeError(msg)


# ---------------------------------------------------------------------------
# Low-level subprocess helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    """Run a command and return CompletedProcess. Raises on non-zero exit."""
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            logger.warning("Command failed [%s]: %s", " ".join(cmd), stderr)
    return result


def _run_ok(cmd: list[str], timeout: int = 15) -> bool:
    """Run a command, return True if exit code is 0."""
    try:
        return _run(cmd, timeout).returncode == 0
    except Exception:
        return False


def _run_out(cmd: list[str], timeout: int = 15) -> str:
    """Run a command, return stripped stdout, or empty string on failure."""
    try:
        result = _run(cmd, timeout)
        return result.stdout.strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Windows helpers
# ---------------------------------------------------------------------------

def _pwsh(script: str) -> str:
    """Run a PowerShell script and return stdout."""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
        creationflags=_NO_WINDOW,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.warning("PowerShell error: %s", stderr)
        raise RuntimeError(stderr or "PowerShell command failed")
    return result.stdout.strip()


def _win_apps_from_ps() -> list[dict]:
    """List windows with titles via PowerShell."""
    script = r"""
Get-Process | Where-Object { $_.MainWindowTitle -ne '' } |
    Select-Object ProcessName, Id, MainWindowTitle |
    Sort-Object ProcessName |
    ConvertTo-Json -Compress
"""
    try:
        raw = _pwsh(script)
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [
            {
                "name": item.get("ProcessName", ""),
                "pid": item.get("Id"),
                "window_title": item.get("MainWindowTitle", ""),
                "platform": "windows",
            }
            for item in data
        ]
    except Exception as e:
        logger.error("_win_apps_from_ps failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Linux helpers
# ---------------------------------------------------------------------------

def _parse_wmctrl_line(line: str) -> Optional[dict]:
    """Parse one wmctrl -l line into {window_id, desktop, host, window_title}."""
    parts = line.split(None, 3)
    if len(parts) < 4:
        return None
    return {
        "window_id": parts[0],
        "desktop": int(parts[1]) if parts[1].isdigit() else -1,
        "host": parts[2],
        "window_title": parts[3],
    }


def _linux_apps_from_wmctrl() -> list[dict]:
    """List windows with titles via wmctrl."""
    if not _check_tool("wmctrl"):
        logger.warning("wmctrl not found. Install: sudo apt install wmctrl")
        return []

    try:
        result = _run(["wmctrl", "-l"], timeout=10)
    except Exception as e:
        logger.warning("wmctrl failed: %s", e)
        return []

    apps = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parsed = _parse_wmctrl_line(line)
        if parsed is None:
            continue
        # Derive app name: everything before " - " in the title, or the first word
        title = parsed["window_title"]
        app_name = title.split(" - ")[0].strip() if " - " in title else ""
        apps.append({
            "name": app_name,
            "window_id": parsed["window_id"],
            "window_title": title,
            "desktop": parsed["desktop"],
            "platform": "linux",
        })
    return apps


def _linux_window_geometry(window_id: str) -> Optional[dict]:
    """Get window geometry via xdotool. Returns {x, y, width, height}."""
    if not _check_tool("xdotool"):
        return None
    try:
        raw = _run_out(["xdotool", "getwindowgeometry", "--shell", window_id])
        geo = {}
        for line in raw.split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                try:
                    geo[k] = int(v)
                except ValueError:
                    geo[k] = v
        if "X" in geo and "Y" in geo and "WIDTH" in geo and "HEIGHT" in geo:
            return {
                "x": geo["X"],
                "y": geo["Y"],
                "width": geo["WIDTH"],
                "height": geo["HEIGHT"],
            }
        return None
    except Exception as e:
        logger.debug("xdotool geometry for %s failed: %s", window_id, e)
        return None


def _linux_window_pid(window_id: str) -> Optional[int]:
    """Get PID of window via xdotool."""
    if not _check_tool("xdotool"):
        return None
    try:
        raw = _run_out(["xdotool", "getwindowpid", window_id])
        return int(raw)
    except Exception:
        return None


def _linux_window_exe(window_id: str) -> Optional[str]:
    """Get executable path of a window's process via /proc."""
    pid = _linux_window_pid(window_id)
    if pid is None:
        return None
    exe_link = Path(f"/proc/{pid}/exe")
    try:
        return str(exe_link.resolve())
    except Exception:
        return None


def _linux_find_window_by_title(pattern: str) -> Optional[str]:
    """Find a window ID whose title contains pattern (case-insensitive)."""
    apps = _linux_apps_from_wmctrl()
    pattern_lower = pattern.lower()
    for app in apps:
        if pattern_lower in app.get("window_title", "").lower():
            return app.get("window_id")
    return None


def _linux_desktop_file_for(app_name: str) -> Optional[Path]:
    """Find a .desktop file that matches an app name."""
    search_name = app_name.lower().replace(" ", "")
    search_dirs = [
        Path("/usr/share/applications"),
        Path.home() / ".local/share/applications",
        Path("/var/lib/flatpak/exports/share/applications"),
        Path.home() / ".local/share/flatpak/exports/share/applications",
    ]
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for desktop_file in sorted(search_dir.glob("*.desktop")):
            stem = desktop_file.stem.lower()
            if search_name in stem or stem.startswith(search_name):
                return desktop_file
            # Also check the Name= line inside
            try:
                content = desktop_file.read_text(encoding="utf-8")
                for line in content.split("\n"):
                    if line.lower().startswith("name="):
                        name_val = line.split("=", 1)[1].strip().lower()
                        if search_name in name_val.replace(" ", ""):
                            return desktop_file
            except Exception:
                continue
    return None


def _linux_desktop_app_info(desktop_file: Path) -> Optional[dict]:
    """Parse .desktop file into {name, exe_path, comment}."""
    try:
        content = desktop_file.read_text(encoding="utf-8")
    except Exception:
        return None
    info = {"name": desktop_file.stem, "exe_path": "", "comment": ""}
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("Name="):
            info["name"] = line.split("=", 1)[1]
        elif line.startswith("Exec="):
            exec_val = line.split("=", 1)[1]
            # Strip field codes like %f %u %F %U
            exec_val = re.sub(r"\s*%[fFuUdDnNickvm]\s*", " ", exec_val).strip()
            info["exe_path"] = exec_val
        elif line.startswith("Comment="):
            info["comment"] = line.split("=", 1)[1]
    return info if info["exe_path"] else None


# ---------------------------------------------------------------------------
# AppInfo dataclass
# ---------------------------------------------------------------------------

@dataclass
class AppInfo:
    name: str
    exe_path: Optional[str] = None
    window_title: Optional[str] = None
    pid: Optional[int] = None
    window_rect: Optional[dict] = None  # {left, top, right, bottom} or {x, y, width, height}
    platform: str = ""


def _to_app_info_dict(info: dict) -> dict:
    """Convert internal dict to standard API response."""
    w = info.get("window_rect") or {}
    return {
        "name": info.get("name", ""),
        "pid": info.get("pid"),
        "window_title": info.get("window_title", ""),
        "exe_path": info.get("exe_path"),
        "window_rect": {
            "left": w.get("left", w.get("x", 0)),
            "top": w.get("top", w.get("y", 0)),
            "right": w.get("right", (w.get("x", 0) + w.get("width", 0))),
            "bottom": w.get("bottom", (w.get("y", 0) + w.get("height", 0))),
        } if w else None,
        "platform": info.get("platform", _platform_name()),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_apps() -> list[dict]:
    """List running applications with window info.

    Returns list of {name, pid, window_title, window_id, platform}.
    """
    if _is_windows():
        return _win_apps_from_ps()
    elif _is_linux():
        return _linux_apps_from_wmctrl()
    return []


def app_info(app_name: str) -> Optional[dict]:
    """Get detailed info about an application by name.

    Returns {name, pid, window_title, window_rect, exe_path, platform} or None.
    """
    if _is_windows():
        return _app_info_windows(app_name)
    elif _is_linux():
        return _app_info_linux(app_name)
    return None


def _app_info_windows(app_name: str) -> Optional[dict]:
    """Windows implementation — PowerShell + Win32 API."""
    script = f"""
$proc = Get-Process -Name "{app_name}" -ErrorAction SilentlyContinue |
    Where-Object {{ $_.MainWindowTitle -ne '' }} |
    Select-Object -First 1
if (-not $proc) {{
    Write-Output "null"
    exit 0
}}
$rect = [PSCustomObject]@{{}}
try {{
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {{
    [DllImport("user32.dll")] public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    public struct RECT {{ public int Left; public int Top; public int Right; public int Bottom; }}
}}
"@
    $hwnd = [Win32]::FindWindow($null, $proc.MainWindowTitle)
    if ($hwnd -ne [IntPtr]::Zero) {{
        $r = New-Object Win32+RECT
        [Win32]::GetWindowRect($hwnd, [ref]$r)
        $rect = @{{ left = $r.Left; top = $r.Top; right = $r.Right; bottom = $r.Bottom }}
    }}
}} catch {{}}
[PSCustomObject]@{{
    name = $proc.ProcessName
    pid = $proc.Id
    window_title = $proc.MainWindowTitle
    exe_path = $proc.Path
    window_rect = $rect
}} | ConvertTo-Json -Compress
"""
    try:
        raw = _pwsh(script)
        if not raw or raw == "null":
            return None
        data = json.loads(raw)
        info = {
            "name": data.get("name", ""),
            "pid": data.get("pid"),
            "window_title": data.get("window_title", ""),
            "exe_path": data.get("exe_path"),
            "window_rect": data.get("window_rect"),
            "platform": "windows",
        }
        return _to_app_info_dict(info)
    except Exception as e:
        logger.error("app_info(%s) on Windows failed: %s", app_name, e)
        return None


def _app_info_linux(app_name: str) -> Optional[dict]:
    """Linux implementation — wmctrl + xdotool."""
    window_id = _linux_find_window_by_title(app_name)
    if window_id is None:
        # Try finding via desktop file
        df = _linux_desktop_file_for(app_name)
        if df:
            d_info = _linux_desktop_app_info(df)
            if d_info:
                return {
                    "name": d_info["name"],
                    "pid": None,
                    "window_title": None,
                    "exe_path": d_info["exe_path"],
                    "window_rect": None,
                    "platform": "linux",
                }
        return None

    geo = _linux_window_geometry(window_id)
    pid = _linux_window_pid(window_id)
    exe = _linux_window_exe(window_id) if window_id else None

    # Get full window title
    apps = _linux_apps_from_wmctrl()
    title = ""
    for app in apps:
        if app.get("window_id") == window_id:
            title = app.get("window_title", "")
            break

    info = {
        "name": app_name,
        "pid": pid,
        "window_title": title,
        "exe_path": exe,
        "window_rect": geo,
        "platform": "linux",
    }
    return _to_app_info_dict(info)


def open_app(app_name: str) -> dict:
    """Open/activate an application. Returns success status.

    Windows: Start-Process or bring to foreground.
    Linux:   gtk-launch / xdg-open, or wmctrl -a to activate running window.
    """
    if _is_windows():
        return _open_app_windows(app_name)
    elif _is_linux():
        return _open_app_linux(app_name)
    return {"success": False, "error": f"Unsupported platform: {_platform_name()}"}


def _open_app_windows(app_name: str) -> dict:
    script = f"""
$proc = Get-Process -Name "{app_name}" -ErrorAction SilentlyContinue |
    Where-Object {{ $_.MainWindowTitle -ne '' }} |
    Select-Object -First 1
if ($proc) {{
    Add-Type @"
using System; using System.Runtime.InteropServices;
public class Win32 {{
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}}
"@
    $hwnd = [Win32]::FindWindow($null, $proc.MainWindowTitle)
    if ($hwnd -ne [IntPtr]::Zero) {{
        [Win32]::ShowWindow($hwnd, 9)
        [Win32]::SetForegroundWindow($hwnd)
        Write-Output "activated"
        exit 0
    }}
}}
Start-Process "{app_name}" -ErrorAction Stop
Write-Output "launched"
"""
    try:
        action = _pwsh(script)
        return {"success": True, "action": action}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _open_app_linux(app_name: str) -> dict:
    """Linux: activate existing window or launch via .desktop / xdg-open."""
    # Strategy 1: Try to activate an already running window
    window_id = _linux_find_window_by_title(app_name)
    if window_id and _check_tool("wmctrl"):
        try:
            _run(["wmctrl", "-i", "-a", window_id])
            return {"success": True, "action": "activated"}
        except Exception:
            pass  # Fall through to launch

    # Strategy 2: Launch via .desktop file
    desktop_file = _linux_desktop_file_for(app_name)
    if desktop_file and _check_tool("gtk-launch"):
        try:
            _run(["gtk-launch", desktop_file.name])
            return {"success": True, "action": "launched", "desktop_file": str(desktop_file)}
        except Exception as e:
            logger.debug("gtk-launch failed: %s", e)

    # Strategy 3: xdg-open (best effort)
    if _check_tool("xdg-open"):
        try:
            _run(["xdg-open", app_name])
            return {"success": True, "action": "launched", "method": "xdg-open"}
        except Exception:
            pass

    # Strategy 4: Try the app_name as a command directly
    if _check_tool(app_name):
        try:
            subprocess.Popen([app_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
            return {"success": True, "action": "launched", "method": "direct"}
        except Exception:
            pass

    return {"success": False, "error": f"Could not find or launch '{app_name}'"}


def close_app(app_name: str) -> dict:
    """Close an application gracefully."""
    if _is_windows():
        return _close_app_windows(app_name)
    elif _is_linux():
        return _close_app_linux(app_name)
    return {"success": False, "error": f"Unsupported platform: {_platform_name()}"}


def _close_app_windows(app_name: str) -> dict:
    script = f"""
$proc = Get-Process -Name "{app_name}" -ErrorAction SilentlyContinue |
    Where-Object {{ $_.MainWindowTitle -ne '' }}
if ($proc) {{
    $proc | ForEach-Object {{ $_.CloseMainWindow() | Out-Null }}
    Start-Sleep -Milliseconds 500
    $proc | ForEach-Object {{
        if (-not $_.HasExited) {{ $_.Kill() }}
    }}
    Write-Output "closed"
}} else {{
    Write-Output "not_found"
}}
"""
    try:
        _pwsh(script)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _close_app_linux(app_name: str) -> dict:
    """Linux: close via wmctrl or xdotool."""
    window_id = _linux_find_window_by_title(app_name)
    if window_id:
        # Try graceful close first
        if _check_tool("wmctrl"):
            result = _run(["wmctrl", "-i", "-c", window_id])
            if result.returncode == 0:
                return {"success": True, "action": "closed"}
        # Force kill
        if _check_tool("xdotool"):
            _run(["xdotool", "windowkill", window_id])
            return {"success": True, "action": "killed"}

    # Try pkill as last resort
    try:
        _run(["pkill", "-f", app_name])
        return {"success": True, "action": "killed"}
    except Exception:
        pass

    return {"success": False, "error": f"Could not close '{app_name}'. Is it running?"}


def app_position(app_name: str) -> Optional[dict]:
    """Get the screen position of an application window."""
    info = app_info(app_name)
    if info and info.get("window_rect"):
        return {
            "app_name": info["name"],
            "window_rect": info["window_rect"],
            "platform": info.get("platform", _platform_name()),
        }
    return None


def list_installed_apps() -> list[dict]:
    """List installed applications.

    Windows: Start Menu .lnk files.
    Linux:   /usr/share/applications/*.desktop + ~/.local/share/applications/.
    """
    if _is_windows():
        return _list_installed_apps_windows()
    elif _is_linux():
        return _list_installed_apps_linux()
    return []


def _list_installed_apps_windows() -> list[dict]:
    script = r"""
$apps = @()
$paths = @(
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs",
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
)
foreach ($path in $paths) {
    if (Test-Path $path) {
        Get-ChildItem -Path $path -Recurse -Filter "*.lnk" -ErrorAction SilentlyContinue |
            ForEach-Object {
                $wsh = New-Object -ComObject WScript.Shell
                $lnk = $wsh.CreateShortcut($_.FullName)
                if ($lnk.TargetPath) {
                    $apps += [PSCustomObject]@{
                        name = $_.BaseName
                        path = $lnk.TargetPath
                    }
                }
            }
    }
}
$apps | ConvertTo-Json -Compress
"""
    try:
        raw = _pwsh(script)
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return data
    except Exception as e:
        logger.error("list_installed_apps (Windows) failed: %s", e)
        return []


def _list_installed_apps_linux() -> list[dict]:
    """Scan .desktop files for installed applications."""
    search_dirs = [
        Path("/usr/share/applications"),
        Path.home() / ".local/share/applications",
        Path("/var/lib/flatpak/exports/share/applications"),
        Path.home() / ".local/share/flatpak/exports/share/applications",
    ]
    apps = []
    seen = set()

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for desktop_file in sorted(search_dir.glob("*.desktop")):
            if desktop_file.name in seen:
                continue
            seen.add(desktop_file.name)

            info = _linux_desktop_app_info(desktop_file)
            if info:
                apps.append({
                    "name": info["name"],
                    "path": info["exe_path"],
                    "desktop_file": str(desktop_file),
                    "comment": info.get("comment", ""),
                })

    return apps
