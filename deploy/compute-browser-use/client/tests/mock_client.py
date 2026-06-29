"""Layer 2: Mock Client Control Plane for integration testing.

This mock simulates the Windows Client Control Plane API so that the server-side
services (AstrBot → Hermes Bridge → Hermes API → cuactl → Client) can be tested
end-to-end in CI without a real Windows machine.

Usage:
    python mock_client.py --port 9110

The mock records all received requests and returns realistic responses.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("mock-client")

# Pre-canned test data
_FAKE_SCREENSHOT_PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
).decode()

_MOCK_APPS = [
    {"name": "chrome", "pid": 1234, "window_title": "Chrome - Google", "platform": "windows"},
    {"name": "notepad", "pid": 5678, "window_title": "Notepad - Untitled", "platform": "windows"},
    {"name": "vscode", "pid": 9012, "window_title": "Visual Studio Code", "platform": "windows"},
    {"name": "explorer", "pid": 3456, "window_title": "File Explorer", "platform": "windows"},
]

_MOCK_INSTALLED_APPS = [
    {"name": "Google Chrome", "path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"},
    {"name": "Visual Studio Code", "path": "C:\\Users\\user\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe"},
    {"name": "Notepad++", "path": "C:\\Program Files\\Notepad++\\notepad++.exe"},
]

# Request recording for test assertions
request_log: list[dict] = []

# Fault injection
_fault_config: dict = {
    "capture_fail": False,
    "click_fail": False,
    "auth_reject": False,
    "slow_response": 0.0,  # seconds of artificial delay
}


def reset_faults():
    """Reset all fault injection settings."""
    global _fault_config
    _fault_config = {
        "capture_fail": False,
        "click_fail": False,
        "auth_reject": False,
        "slow_response": 0.0,
    }


def set_fault(key: str, value):
    _fault_config[key] = value


def get_request_log() -> list[dict]:
    return list(request_log)


def clear_request_log():
    request_log.clear()


# ---------------------------------------------------------------------------
# FastAPI Mock App
# ---------------------------------------------------------------------------

app = FastAPI(title="Mock CUA Control Plane", version="0.1.0")

MOCK_TOKEN = os.environ.get("MOCK_CLIENT_TOKEN", "test-mock-token")


@app.middleware("http")
async def log_and_auth(request: Request, call_next):
    # Record request
    body = None
    try:
        body = await request.json()
    except Exception:
        pass
    request_log.append({
        "method": request.method,
        "path": request.url.path,
        "body": body,
        "time": time.time(),
    })

    # Fault: auth rejection
    if _fault_config["auth_reject"]:
        return JSONResponse(status_code=403, content={"error": "Access Denied", "detail": "Fault injection: auth_reject"})

    # Auth check
    if request.url.path not in ("/health", "/api/v1/health", "/_admin/reset", "/_admin/faults"):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not token or token != MOCK_TOKEN:
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    # Fault: slow response
    if _fault_config["slow_response"] > 0:
        time.sleep(_fault_config["slow_response"])

    return await call_next(request)


# -- Admin endpoints (for test control) --

@app.post("/_admin/reset")
async def admin_reset():
    clear_request_log()
    reset_faults()
    return {"status": "reset"}


@app.post("/_admin/faults")
async def admin_set_faults(req: dict):
    for key, value in req.items():
        if key in _fault_config:
            _fault_config[key] = value
    return {"faults": dict(_fault_config)}


@app.get("/_admin/requests")
async def admin_requests():
    return {"count": len(request_log), "requests": request_log}


# -- Health --

@app.get("/health")
@app.get("/api/v1/health")
async def health():
    return {
        "status": "ok",
        "service": "mock-cua-control-plane",
        "permissions": {
            "permission_level": "full",
            "allowed_operations": sorted([
                "capture", "list_apps", "app_info", "app_position",
                "click", "type", "press_key", "move", "scroll", "drag",
                "open_app", "close_app",
            ]),
        },
    }


# -- Deterministic Operations --

@app.post("/api/v1/dops/list_apps")
async def list_apps():
    return {"success": True, "apps": _MOCK_APPS}


@app.post("/api/v1/dops/list_installed_apps")
async def list_installed_apps():
    return {"success": True, "apps": _MOCK_INSTALLED_APPS}


@app.post("/api/v1/dops/app_info")
async def app_info(req: dict):
    app_name = req.get("app_name", "")
    for app in _MOCK_APPS:
        if app["name"].lower() == app_name.lower():
            return {
                "success": True,
                "info": {
                    "name": app["name"],
                    "pid": app["pid"],
                    "window_title": app["window_title"],
                    "exe_path": f"C:\\Program Files\\{app['name']}\\{app['name']}.exe",
                    "window_rect": {"left": 100, "top": 100, "right": 900, "bottom": 700},
                    "platform": "windows",
                },
            }
    return {"success": False, "error": f"App '{app_name}' not found"}


@app.post("/api/v1/dops/app_position")
async def app_position(req: dict):
    app_name = req.get("app_name", "")
    for app in _MOCK_APPS:
        if app["name"].lower() == app_name.lower():
            return {
                "success": True,
                "app_name": app["name"],
                "window_rect": {"left": 100, "top": 200, "right": 900, "bottom": 700},
                "platform": "windows",
            }
    return {"success": False, "error": f"Cannot get position for '{app_name}'"}


@app.post("/api/v1/dops/open_app")
async def open_app(req: dict):
    return {"success": True, "action": "launched"}


@app.post("/api/v1/dops/close_app")
async def close_app(req: dict):
    return {"success": True}


# -- CUA Operations --

@app.post("/api/v1/cua/capture")
async def capture():
    if _fault_config["capture_fail"]:
        return {"success": False, "error": "Fault injection: capture_fail"}
    return {
        "success": True,
        "base64": _FAKE_SCREENSHOT_PNG,
        "mime_type": "image/png",
    }


@app.post("/api/v1/cua/screen_size")
async def screen_size():
    return {"success": True, "width": 1920, "height": 1080}


@app.post("/api/v1/cua/click")
async def click(req: dict):
    if _fault_config["click_fail"]:
        return {"success": False, "error": "Fault injection: click_fail"}
    return {
        "success": True,
        "x": req.get("x", 0),
        "y": req.get("y", 0),
        "button": req.get("button", "left"),
    }


@app.post("/api/v1/cua/move")
async def move(req: dict):
    return {"success": True, "x": req.get("x", 0), "y": req.get("y", 0)}


@app.post("/api/v1/cua/scroll")
async def scroll(req: dict):
    return {"success": True, "dx": req.get("dx", 0), "dy": req.get("dy", 0)}


@app.post("/api/v1/cua/drag")
async def drag(req: dict):
    return {"success": True}


@app.post("/api/v1/cua/type")
async def type_text(req: dict):
    return {"success": True, "text": req.get("text", "")}


@app.post("/api/v1/cua/press_key")
async def press_key(req: dict):
    return {"success": True, "key": req.get("key", "")}


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9110)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
