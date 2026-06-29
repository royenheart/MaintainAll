"""FastAPI REST API for the CUA Control Plane.

Exposes deterministic operations and CUA actions with permission enforcement.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import cua_core, deterministic_ops
from .config import get_config
from .permissions import AccessDeniedError, check_permission, get_allowed_ops

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CUA Control Plane",
    version="0.1.0",
    description="Local PC desktop control service for remote AI agents",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    cfg = get_config()
    # Skip auth for health check and OPTIONS
    if request.url.path in ("/api/v1/health", "/health") or request.method == "OPTIONS":
        return await call_next(request)

    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token or token != cfg.local_token:
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "detail": "Invalid or missing Bearer token"},
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@app.exception_handler(AccessDeniedError)
async def access_denied_handler(request: Request, exc: AccessDeniedError):
    return JSONResponse(
        status_code=403,
        content={"error": "Access Denied", "detail": exc.reason},
    )


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------

@app.get("/health")
@app.get("/api/v1/health")
async def health():
    return {
        "status": "ok",
        "service": "cua-control-plane",
        "permissions": get_allowed_ops(),
    }


# ---------------------------------------------------------------------------
# Deterministic Operations
# ---------------------------------------------------------------------------

@app.post("/api/v1/dops/list_apps")
async def api_list_apps():
    check_permission("list_apps")
    return {"success": True, "apps": deterministic_ops.list_apps()}


@app.post("/api/v1/dops/list_installed_apps")
async def api_list_installed_apps():
    check_permission("list_apps")
    return {"success": True, "apps": deterministic_ops.list_installed_apps()}


@app.post("/api/v1/dops/app_info")
async def api_app_info(req: dict):
    check_permission("app_info")
    app_name = req.get("app_name", "")
    info = deterministic_ops.app_info(app_name)
    if info is None:
        return {"success": False, "error": f"App '{app_name}' not found"}
    return {"success": True, "info": info}


@app.post("/api/v1/dops/app_position")
async def api_app_position(req: dict):
    check_permission("app_position")
    app_name = req.get("app_name", "")
    pos = deterministic_ops.app_position(app_name)
    if pos is None:
        return {"success": False, "error": f"Cannot get position for '{app_name}'"}
    return {"success": True, **pos}


@app.post("/api/v1/dops/open_app")
async def api_open_app(req: dict):
    check_permission("open_app")
    app_name = req.get("app_name", "")
    return deterministic_ops.open_app(app_name)


@app.post("/api/v1/dops/close_app")
async def api_close_app(req: dict):
    check_permission("close_app")
    app_name = req.get("app_name", "")
    return deterministic_ops.close_app(app_name)


# ---------------------------------------------------------------------------
# CUA Operations
# ---------------------------------------------------------------------------

@app.post("/api/v1/cua/capture")
async def api_capture():
    check_permission("capture")
    return await cua_core.capture()


@app.post("/api/v1/cua/screen_size")
async def api_screen_size():
    check_permission("capture")
    return await cua_core.screen_size()


@app.post("/api/v1/cua/click")
async def api_click(req: dict):
    check_permission("click")
    x = int(req.get("x", 0))
    y = int(req.get("y", 0))
    button = req.get("button", "left")
    return await cua_core.click(x, y, button)


@app.post("/api/v1/cua/move")
async def api_move(req: dict):
    check_permission("move")
    x = int(req.get("x", 0))
    y = int(req.get("y", 0))
    return await cua_core.move(x, y)


@app.post("/api/v1/cua/scroll")
async def api_scroll(req: dict):
    check_permission("scroll")
    dx = int(req.get("dx", 0))
    dy = int(req.get("dy", 0))
    return await cua_core.scroll(dx, dy)


@app.post("/api/v1/cua/drag")
async def api_drag(req: dict):
    check_permission("drag")
    from_x = int(req.get("from_x", 0))
    from_y = int(req.get("from_y", 0))
    to_x = int(req.get("to_x", 0))
    to_y = int(req.get("to_y", 0))
    return await cua_core.drag(from_x, from_y, to_x, to_y)


@app.post("/api/v1/cua/type")
async def api_type(req: dict):
    check_permission("type")
    text = req.get("text", "")
    return await cua_core.type_text(text)


@app.post("/api/v1/cua/press_key")
async def api_press_key(req: dict):
    check_permission("press_key")
    key = req.get("key", "")
    return await cua_core.press_key(key)
