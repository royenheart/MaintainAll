"""Multi-screen detection and management.

Supports:
  - Windows: EnumDisplayMonitors via ctypes
  - Linux:   xrandr (X11) or wlr-randr (Wayland)
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
from ctypes import wintypes
from typing import Any

logger = logging.getLogger(__name__)


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


_MONITORINFOF_PRIMARY = 1
_screens_cache: list[dict[str, Any]] | None = None


def _get_screens_windows() -> list[dict[str, Any]]:
    screens: list[dict[str, Any]] = []
    index = [0]

    def _callback(hMonitor, hdc, lprcMonitor, dwData):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(info)):
            screens.append({
                "index": index[0],
                "name": info.szDevice.rstrip("\x00"),
                "x": info.rcMonitor.left,
                "y": info.rcMonitor.top,
                "width": info.rcMonitor.right - info.rcMonitor.left,
                "height": info.rcMonitor.bottom - info.rcMonitor.top,
                "is_primary": bool(info.dwFlags & _MONITORINFOF_PRIMARY),
            })
            index[0] += 1
        return True

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )
    try:
        ctypes.windll.user32.EnumDisplayMonitors(
            None, None, MonitorEnumProc(_callback), 0
        )
    except Exception as e:
        logger.warning("EnumDisplayMonitors failed: %s", e)

    if not screens:
        screens.append(_fallback_screen())

    return screens


def _get_screens_linux() -> list[dict[str, Any]]:
    screens: list[dict[str, Any]] = []
    try:
        out = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True, text=True, timeout=5,
        )
        current = {}
        for line in out.stdout.split("\n"):
            line = line.strip()
            if " connected" in line:
                parts = line.split()
                current = {"name": parts[0], "is_primary": "primary" in line}
            elif current and ("*" in line or "+" in line) and "x" in line:
                mode_part = line.split()[0]
                if "x" in mode_part:
                    w, h = mode_part.split("x")
                    xy = line.split()
                    x_pos, y_pos = 0, 0
                    for t in xy:
                        if t.startswith("+") and t not in (mode_part, "+0+0"):
                            pos = t.split("+")
                            if len(pos) >= 3:
                                x_pos, y_pos = int(pos[1]), int(pos[2])
                    current.update({
                        "width": int(w), "height": int(h),
                        "x": x_pos, "y": y_pos,
                    })
                    screens.append(current)
                    current = {}
    except Exception as e:
        logger.warning("xrandr failed: %s", e)

    if not screens:
        screens.append(_fallback_screen())
    else:
        for i, s in enumerate(screens):
            s["index"] = i

    return screens


def _fallback_screen() -> dict[str, Any]:
    return {
        "index": 0,
        "name": "DISPLAY1",
        "x": 0, "y": 0,
        "width": 1920, "height": 1080,
        "is_primary": True,
    }


def get_screens(refresh: bool = False) -> list[dict[str, Any]]:
    global _screens_cache
    if _screens_cache is not None and not refresh:
        return _screens_cache

    if os.name == "nt":
        _screens_cache = _get_screens_windows()
    else:
        _screens_cache = _get_screens_linux()

    return _screens_cache


def get_screen_bounds() -> dict[str, int]:
    """Get the total bounding box of all screens."""
    screens = get_screens()
    if not screens:
        return {"x": 0, "y": 0, "width": 1920, "height": 1080}
    left = min(s["x"] for s in screens)
    top = min(s["y"] for s in screens)
    right = max(s["x"] + s["width"] for s in screens)
    bottom = max(s["y"] + s["height"] for s in screens)
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def is_screen_allowed(x: int, y: int, allowed_indices: list[int] | None = None) -> bool:
    """Check if a coordinate falls within an allowed screen.

    If allowed_indices is None or empty, all screens are allowed.
    """
    screens = get_screens()
    if not allowed_indices:
        return True
    for s in screens:
        if s["index"] in allowed_indices:
            if s["x"] <= x < s["x"] + s["width"] and s["y"] <= y < s["y"] + s["height"]:
                return True
    return False
