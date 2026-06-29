"""Screen capture, mouse, and keyboard operations.

Primary:  cua-driver CLI (background automation via UIA, no focus stealing)
          Used for: screen_size, background click/move/scroll/type/press_key
Fallback: native PIL + ctypes (always available on Windows)
          Used for: full-screen capture, foreground fallback when cua-driver unavailable
"""

from __future__ import annotations

import base64
import ctypes
import io
import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_driver_binary: Optional[str] = None
_driver_available_checked: bool = False
_daemon_started: bool = False
_window_cache: list[dict] = []
_window_cache_time: float = 0.0
_WINDOW_CACHE_TTL = 2.0

_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040
_MOUSEEVENTF_WHEEL = 0x0800
_WHEEL_DELTA = 120

_solo_blocked: bool = False
_solo_last_manual: float = 0.0


def _find_driver() -> Optional[str]:
    global _driver_binary, _driver_available_checked
    if _driver_available_checked:
        return _driver_binary
    _driver_available_checked = True
    candidates = [
        shutil.which("cua-driver"),
        shutil.which("cua-driver.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Cua", "cua-driver", "bin", "cua-driver.exe"),
        os.path.join(os.environ.get("USERPROFILE", ""), ".cua-driver", "packages", "current", "cua-driver.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            logger.info("cua-driver found: %s", path)
            _driver_binary = path
            return path
    logger.info("cua-driver not found; using native fallback")
    return None


def _driver_call(tool: str, args: dict, timeout_sec: int = 15) -> Optional[dict]:
    binary = _find_driver()
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "call", tool, json.dumps(args)],
            capture_output=True, text=True, timeout=timeout_sec,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"_raw": result.stdout.strip()}
        else:
            logger.warning("cua-driver %s failed (rc=%d): %s", tool, result.returncode, result.stderr.strip()[:200])
            return None
    except FileNotFoundError:
        _driver_binary = None
        return None
    except subprocess.TimeoutExpired:
        logger.warning("cua-driver %s timed out", tool)
        return None
    except Exception as e:
        logger.warning("cua-driver %s error: %s", tool, e)
        return None


def _driver_available() -> bool:
    return _find_driver() is not None


def check_cua_available() -> bool:
    return _driver_available()


def check_uia_available() -> bool:
    """Check if cua-driver daemon has UIAccess (elevated integrity)."""
    binary = _find_driver()
    if not binary:
        return False
    try:
        data = _get_driver_json("check_permissions", {}, timeout_sec=10)
        if data:
            return bool(data.get("elevated"))
    except Exception:
        pass
    return False


def get_last_input_seconds() -> float:
    """Seconds since last user input (Windows GetLastInputInfo)."""
    if os.name != "nt":
        return 0.0
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        tick = ctypes.windll.kernel32.GetTickCount()
        delta = (tick - lii.dwTime) & 0xFFFFFFFF
        return delta / 1000.0
    return 0.0


def get_control_mode() -> dict:
    """Return current control mode and status."""
    from .config import get_config as _get_cfg
    cfg = _get_cfg()
    mode = cfg.control_mode
    idle = get_last_input_seconds()
    if mode == "solo":
        global _solo_blocked, _solo_last_manual
        if idle < cfg.solo_idle_timeout:
            _solo_blocked = True
            _solo_last_manual = time.time()
        return {
            "mode": "solo",
            "blocked": _solo_blocked,
            "idle_seconds": round(idle, 1),
            "timeout": cfg.solo_idle_timeout,
            "remaining": max(0, round(cfg.solo_idle_timeout - idle, 1)),
        }
    return {"mode": "collaborative", "blocked": False, "idle_seconds": round(idle, 1)}


def solo_check_access() -> Optional[dict]:
    """Check if external access is allowed in solo mode. 
    Returns None if allowed, error dict if blocked."""
    from .config import get_config as _get_cfg
    cfg = _get_cfg()
    if cfg.control_mode != "solo":
        return None
    global _solo_blocked, _solo_last_manual
    idle = get_last_input_seconds()
    if idle < cfg.solo_idle_timeout:
        _solo_blocked = True
        _solo_last_manual = time.time()
    if _solo_blocked:
        remaining = max(0, round(cfg.solo_idle_timeout - idle, 1))
        if remaining > 0:
            return {
                "success": False, "error": "solo_mode_blocked",
                "message": f"Solo mode: manual input detected. Blocked for {remaining}s. Move cursor or press any key again to reset timer.",
                "idle_seconds": round(idle, 1),
                "timeout": cfg.solo_idle_timeout,
            }
        _solo_blocked = False
    return None


def _ensure_daemon() -> bool:
    global _daemon_started
    if _daemon_started:
        return True
    binary = _find_driver()
    if not binary:
        return False
    try:
        result = subprocess.run([binary, "status"], capture_output=True, text=True, timeout=5)
        if "is running" in result.stdout:
            _daemon_started = True
            logger.info("cua-driver daemon already running")
            return True
    except Exception:
        pass
    try:
        subprocess.Popen([binary, "serve"], creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        time.sleep(2)
        _daemon_started = True
        logger.info("cua-driver daemon started")
        return True
    except Exception as e:
        logger.warning("Failed to start cua-driver daemon: %s", e)
        return False


def start_daemon():
    """Start the cua-driver daemon if available. Call once at app startup."""
    if _driver_available():
        _ensure_daemon()


def _get_driver_json(tool: str, args: dict, timeout_sec: int = 10) -> Optional[Any]:
    r = _driver_call(tool, args, timeout_sec=timeout_sec)
    if not r:
        return None
    try:
        return json.loads(r["_raw"])
    except (json.JSONDecodeError, AttributeError):
        return None


def _refresh_window_cache() -> list[dict]:
    global _window_cache, _window_cache_time
    now = time.time()
    if _window_cache and (now - _window_cache_time) < _WINDOW_CACHE_TTL:
        return _window_cache
    data = _get_driver_json("get_accessibility_tree", {})
    if data and isinstance(data.get("windows"), list):
        _window_cache = data["windows"]
        _window_cache_time = now
    return _window_cache


def _find_window_at_point(x: int, y: int) -> Optional[dict]:
    best = None
    best_z = -1
    skip_titles = {"Cua.AgentCursorOverlay", "CuaDriver", "cua-driver"}
    for w in _refresh_window_cache():
        title = w.get("title", "")
        if any(s in title for s in skip_titles):
            continue
        wx, wy = w.get("x", 0), w.get("y", 0)
        ww, wh = w.get("width", 0), w.get("height", 0)
        z = w.get("z_index", 0)
        if wx <= x < wx + ww and wy <= y < wy + wh:
            if z > best_z:
                best = w
                best_z = z
    return best


def _driver_background_click(x: int, y: int, button: str = "left") -> Optional[dict]:
    w = _find_window_at_point(x, y)
    if not w:
        logger.info("cua-driver: no window at (%d, %d)", x, y)
        return None
    pid = w.get("pid")
    window_id = w.get("window_id")
    local_x = x - w.get("x", 0)
    local_y = y - w.get("y", 0)
    logger.info("cua-driver: background %s click at pid=%d window_id=%d local=(%d,%d) screen=(%d,%d)",
                button, pid, window_id, local_x, local_y, x, y)

    dispatch = "background"
    if not check_uia_available():
        dispatch = "background"
    else:
        dispatch = "auto"
    r = _driver_call("click", {
        "pid": pid,
        "window_id": window_id,
        "x": local_x,
        "y": local_y,
        "button": button,
        "dispatch": dispatch,
    })
    if r:
        raw = r.get("_raw", "")
        method = "injected" if "Injected" in raw else "background"
        return {"success": True, "x": x, "y": y, "button": button, "driver": "cua-driver", "method": method}
    return None


def _driver_background_drag(from_x: int, from_y: int, to_x: int, to_y: int) -> Optional[dict]:
    w = _find_window_at_point(from_x, from_y)
    if not w:
        return None
    pid = w.get("pid")
    window_id = w.get("window_id")
    local_from_x = from_x - w.get("x", 0)
    local_from_y = from_y - w.get("y", 0)
    local_to_x = to_x - w.get("x", 0)
    local_to_y = to_y - w.get("y", 0)
    r = _driver_call("drag", {
        "pid": pid,
        "window_id": window_id,
        "from_x": local_from_x,
        "from_y": local_from_y,
        "to_x": local_to_x,
        "to_y": local_to_y,
        "dispatch": "background",
    })
    if r:
        return {"success": True, "from": [from_x, from_y], "to": [to_x, to_y], "driver": "cua-driver"}
    return None


def _driver_background_scroll(dx: int = 0, dy: int = 0) -> Optional[dict]:
    r = _driver_call("scroll", {"dx": dx, "dy": dy, "dispatch": "background"})
    if r:
        return {"success": True, "dx": dx, "dy": dy, "driver": "cua-driver"}
    return None


def _find_top_window() -> Optional[dict]:
    windows = _refresh_window_cache()
    if not windows:
        return None
    skip_titles = {"Cua.AgentCursorOverlay", "CuaDriver", "cua-driver"}
    filtered = [w for w in windows if not any(s in w.get("title", "") for s in skip_titles)]
    if not filtered:
        return None
    return max(filtered, key=lambda w: w.get("z_index", -999))


def _driver_background_type(text: str) -> Optional[dict]:
    w = _find_top_window()
    if not w:
        return None
    r = _driver_call("type_text", {
        "pid": w.get("pid"),
        "window_id": w.get("window_id"),
        "text": text,
        "dispatch": "background",
    }, timeout_sec=10)
    if r:
        return {"success": True, "text": text, "driver": "cua-driver"}
    return None


def _driver_background_press_key(key: str) -> Optional[dict]:
    w = _find_top_window()
    if not w:
        return None
    r = _driver_call("press_key", {
        "pid": w.get("pid"),
        "window_id": w.get("window_id"),
        "key": key,
        "dispatch": "background",
    }, timeout_sec=10)
    if r:
        return {"success": True, "key": key, "driver": "cua-driver"}
    return None


# ---------------------------------------------------------------------------
# Native fallback implementations (Windows only)
# ---------------------------------------------------------------------------

def _native_capture() -> dict:
    from PIL import ImageGrab
    img = ImageGrab.grab(all_screens=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {"success": True, "base64": base64.b64encode(buf.getvalue()).decode(), "mime_type": "image/png"}


def _native_screen_size() -> dict:
    if os.name == "nt":
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        return {"success": True, "width": w, "height": h}
    from PIL import ImageGrab
    img = ImageGrab.grab(all_screens=True)
    return {"success": True, "width": img.width, "height": img.height}


def _native_click(x: int, y: int, button: str = "left") -> dict:
    if os.name != "nt":
        return {"success": False, "error": "Native click only on Windows"}
    ctypes.windll.user32.SetCursorPos(x, y)
    time.sleep(0.01)
    if button == "left":
        ctypes.windll.user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.02)
        ctypes.windll.user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    elif button == "right":
        ctypes.windll.user32.mouse_event(_MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        time.sleep(0.02)
        ctypes.windll.user32.mouse_event(_MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
    elif button == "middle":
        ctypes.windll.user32.mouse_event(_MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
        time.sleep(0.02)
        ctypes.windll.user32.mouse_event(_MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
    return {"success": True, "x": x, "y": y, "button": button}


def _native_move(x: int, y: int) -> dict:
    if os.name != "nt":
        return {"success": False, "error": "Native move only on Windows"}
    ctypes.windll.user32.SetCursorPos(x, y)
    return {"success": True, "x": x, "y": y}


def _native_scroll(dx: int = 0, dy: int = 0) -> dict:
    if os.name != "nt":
        return {"success": False, "error": "Native scroll only on Windows"}
    if dy:
        ctypes.windll.user32.mouse_event(_MOUSEEVENTF_WHEEL, 0, 0, dy * _WHEEL_DELTA, 0)
    if dx:
        ctypes.windll.user32.mouse_event(_MOUSEEVENTF_WHEEL | 0x01000, 0, 0, dx * _WHEEL_DELTA, 0)
    return {"success": True, "dx": dx, "dy": dy}


def _native_drag(from_x: int, from_y: int, to_x: int, to_y: int) -> dict:
    if os.name != "nt":
        return {"success": False, "error": "Native drag only on Windows"}
    ctypes.windll.user32.SetCursorPos(from_x, from_y)
    time.sleep(0.01)
    ctypes.windll.user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    steps = 20
    for i in range(1, steps + 1):
        ix = from_x + (to_x - from_x) * i // steps
        iy = from_y + (to_y - from_y) * i // steps
        ctypes.windll.user32.SetCursorPos(ix, iy)
        time.sleep(0.005)
    time.sleep(0.01)
    ctypes.windll.user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return {"success": True, "from": [from_x, from_y], "to": [to_x, to_y]}


def _native_type_text(text: str) -> dict:
    if os.name != "nt":
        return {"success": False, "error": "Native typing only on Windows"}
    escaped = text.replace('"', '""').replace('%', '%%')
    script = 'Add-Type -AssemblyName System.Windows.Forms;' + f'[System.Windows.Forms.SendKeys]::SendWait("{escaped}")'
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=10)
        return {"success": True, "text": text}
    except Exception as e:
        logger.error("type_text failed: %s", e)
        return {"success": False, "error": str(e)}


def _native_press_key(key: str) -> dict:
    if os.name != "nt":
        return {"success": False, "error": "Native key press only on Windows"}
    key_map = {
        "enter": "{ENTER}", "tab": "{TAB}", "escape": "{ESC}", "esc": "{ESC}",
        "backspace": "{BS}", "delete": "{DEL}", "space": " ",
        "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}",
        "home": "{HOME}", "end": "{END}", "pageup": "{PGUP}", "pagedown": "{PGDN}",
        "f1": "{F1}", "f2": "{F2}", "f3": "{F3}", "f4": "{F4}", "f5": "{F5}",
        "f6": "{F6}", "f7": "{F7}", "f8": "{F8}", "f9": "{F9}", "f10": "{F10}",
        "f11": "{F11}", "f12": "{F12}",
    }
    send_key = key_map.get(key.lower(), "{" + key.upper() + "}")
    script = 'Add-Type -AssemblyName System.Windows.Forms;' + f'[System.Windows.Forms.SendKeys]::SendWait("{send_key}")'
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=5)
        return {"success": True, "key": key}
    except Exception as e:
        logger.error("press_key(%s) failed: %s", key, e)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Public API — cua-driver first, native fallback
# ---------------------------------------------------------------------------

async def capture() -> dict:
    try:
        return _native_capture()
    except Exception as e:
        logger.error("capture failed: %s", e)
        return {"success": False, "error": str(e)}


async def screen_size() -> dict:
    data = _get_driver_json("get_screen_size", {})
    if data and "width" in data and "height" in data:
        return {"success": True, "width": data["width"], "height": data["height"], "driver": "cua-driver"}
    return _native_screen_size()


async def click(x: int, y: int, button: str = "left") -> dict:
    blocked = solo_check_access()
    if blocked:
        return blocked
    from .config import get_config as _get_cfg
    if _get_cfg().control_mode == "solo":
        return _native_click(x, y, button)
    if _driver_available():
        result = _driver_background_click(x, y, button)
        if result:
            return result
    return _native_click(x, y, button)


async def move(x: int, y: int) -> dict:
    blocked = solo_check_access()
    if blocked:
        return blocked
    return _native_move(x, y)


async def scroll(dx: int = 0, dy: int = 0) -> dict:
    blocked = solo_check_access()
    if blocked:
        return blocked
    if _driver_available():
        result = _driver_background_scroll(dx, dy)
        if result:
            return result
    return _native_scroll(dx, dy)


async def drag(from_x: int, from_y: int, to_x: int, to_y: int) -> dict:
    blocked = solo_check_access()
    if blocked:
        return blocked
    if _driver_available():
        result = _driver_background_drag(from_x, from_y, to_x, to_y)
        if result:
            return result
    return _native_drag(from_x, from_y, to_x, to_y)


async def type_text(text: str) -> dict:
    blocked = solo_check_access()
    if blocked:
        return blocked
    if _driver_available():
        result = _driver_background_type(text)
        if result:
            return result
    return _native_type_text(text)


async def press_key(key: str) -> dict:
    blocked = solo_check_access()
    if blocked:
        return blocked
    if _driver_available():
        result = _driver_background_press_key(key)
        if result:
            return result
    return _native_press_key(key)


async def shutdown() -> None:
    pass
