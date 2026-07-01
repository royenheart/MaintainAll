"""CUA Relay — HTTP microservice bridging AI agents to the remote Client
Control Plane.

Runs as a standalone FastAPI service (default mode) **or** as the legacy
`cuactl` CLI (when invoked with `python relay_server.py <command>`).

HTTP mode (containerized, recommended):
    uvicorn relay_server:app --host 0.0.0.0 --port 8000
    POST /cuactl/capture
    POST /cuactl/click        {"x":100,"y":200,"button":"left"}
    POST /cuactl/list-apps
    GET  /health

CLI mode (host debugging, legacy):
    python relay_server.py capture
    python relay_server.py click 100 200
    python relay_server.py list-apps

Each call translates to an HTTPS request to the remote Client Control
Plane running on the Windows PC.

Configuration via environment variables:
    CUACTL_ENDPOINT  — Client Control Plane URL (default: http://127.0.0.1:9110)
    CUACTL_TOKEN     — Client auth token
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from typing import Any, Optional

import httpx

logger = logging.getLogger("cuactl")

DEFAULT_ENDPOINT = os.environ.get("CUACTL_ENDPOINT", "http://127.0.0.1:9110")
DEFAULT_TOKEN = os.environ.get("CUACTL_TOKEN", "")

# Connect timeout kept short so an unreachable client PC fails fast with a
# clear error instead of hanging 120s on Linux TCP SYN retries. Read timeout
# is longer because screenshot/base64 payloads can be sizable.
_REQUEST_TIMEOUT = httpx.Timeout(15.0, read=60.0, write=30.0, pool=15.0)


class CuaClient:
    """HTTP client for the remote CUA Control Plane."""

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, token: str = DEFAULT_TOKEN):
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=_REQUEST_TIMEOUT,
            )
        return self._client

    async def _post(self, path: str, json_data: dict | None = None) -> dict:
        url = f"{self.endpoint}{path}"
        try:
            resp = await self.client.post(url, json=json_data or {})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"HTTP {e.response.status_code}: {e.response.text[:500]}"}
        except httpx.ConnectError as e:
            return {
                "success": False,
                "error": f"client PC unreachable at {self.endpoint}: {e}",
            }
        except httpx.ReadTimeout:
            return {"success": False, "error": f"client PC read timeout at {self.endpoint}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def close(self):
        if self._client:
            await self._client.aclose()

    # -- CUA operations --

    async def capture(self) -> dict:
        """Take a screenshot."""
        result = await self._post("/api/v1/cua/capture")
        if result.get("success") and result.get("base64"):
            import tempfile
            path = os.path.join(tempfile.gettempdir(), f"cuactl_capture_{os.getpid()}.png")
            with open(path, "wb") as f:
                f.write(base64.b64decode(result["base64"]))
            result["file_path"] = path
        return result

    async def screen_size(self) -> dict:
        return await self._post("/api/v1/cua/screen_size")

    async def click(self, x: int, y: int, button: str = "left") -> dict:
        return await self._post("/api/v1/cua/click", {"x": x, "y": y, "button": button})

    async def move(self, x: int, y: int) -> dict:
        return await self._post("/api/v1/cua/move", {"x": x, "y": y})

    async def scroll(self, dx: int = 0, dy: int = 0) -> dict:
        return await self._post("/api/v1/cua/scroll", {"dx": dx, "dy": dy})

    async def drag(self, from_x: int, from_y: int, to_x: int, to_y: int) -> dict:
        return await self._post("/api/v1/cua/drag", {
            "from_x": from_x, "from_y": from_y,
            "to_x": to_x, "to_y": to_y,
        })

    async def type_text(self, text: str) -> dict:
        return await self._post("/api/v1/cua/type", {"text": text})

    async def press_key(self, key: str) -> dict:
        return await self._post("/api/v1/cua/press_key", {"key": key})

    # -- Deterministic operations --

    async def list_apps(self) -> dict:
        return await self._post("/api/v1/dops/list_apps")

    async def list_installed_apps(self) -> dict:
        return await self._post("/api/v1/dops/list_installed_apps")

    async def app_info(self, app_name: str) -> dict:
        return await self._post("/api/v1/dops/app_info", {"app_name": app_name})

    async def app_position(self, app_name: str) -> dict:
        return await self._post("/api/v1/dops/app_position", {"app_name": app_name})

    async def open_app(self, app_name: str) -> dict:
        return await self._post("/api/v1/dops/open_app", {"app_name": app_name})

    async def close_app(self, app_name: str) -> dict:
        return await self._post("/api/v1/dops/close_app", {"app_name": app_name})


# ---------------------------------------------------------------------------
# FastAPI app (HTTP microservice mode)
# ---------------------------------------------------------------------------
#
# Lazy import so the CLI mode still works on hosts that only have httpx
# installed (not fastapi/uvicorn). The container image installs the full set.
try:
    from fastapi import FastAPI
    from pydantic import BaseModel, Field

    app = FastAPI(
        title="CUA Relay",
        description="HTTP bridge to the remote Client Control Plane.",
        version="2.0.0",
    )

    # Reuse one client for the lifetime of the HTTP service. httpx's
    # AsyncClient pools connections; recreating it per request would defeat
    # pooling and leak sockets under load.
    _service_client = CuaClient()

    class ClickBody(BaseModel):
        x: int
        y: int
        button: str = "left"

    class MoveBody(BaseModel):
        x: int
        y: int

    class ScrollBody(BaseModel):
        dx: int = 0
        dy: int = 0

    class DragBody(BaseModel):
        from_x: int = Field(..., alias="from_x")
        from_y: int
        to_x: int
        to_y: int

    class TextBody(BaseModel):
        text: str

    class KeyBody(BaseModel):
        key: str

    class AppNameBody(BaseModel):
        app_name: str

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "endpoint": _service_client.endpoint,
            "token_configured": bool(_service_client.token),
        }

    @app.post("/cuactl/capture")
    async def http_capture() -> dict:
        return await _service_client.capture()

    @app.post("/cuactl/screen-size")
    async def http_screen_size() -> dict:
        return await _service_client.screen_size()

    @app.post("/cuactl/click")
    async def http_click(body: ClickBody) -> dict:
        return await _service_client.click(body.x, body.y, body.button)

    @app.post("/cuactl/move")
    async def http_move(body: MoveBody) -> dict:
        return await _service_client.move(body.x, body.y)

    @app.post("/cuactl/scroll")
    async def http_scroll(body: ScrollBody) -> dict:
        return await _service_client.scroll(body.dx, body.dy)

    @app.post("/cuactl/drag")
    async def http_drag(body: DragBody) -> dict:
        return await _service_client.drag(body.from_x, body.from_y, body.to_x, body.to_y)

    @app.post("/cuactl/type")
    async def http_type(body: TextBody) -> dict:
        return await _service_client.type_text(body.text)

    @app.post("/cuactl/press_key")
    async def http_press_key(body: KeyBody) -> dict:
        return await _service_client.press_key(body.key)

    @app.post("/cuactl/list-apps")
    async def http_list_apps() -> dict:
        return await _service_client.list_apps()

    @app.post("/cuactl/list-installed-apps")
    async def http_list_installed_apps() -> dict:
        return await _service_client.list_installed_apps()

    @app.post("/cuactl/app-info")
    async def http_app_info(body: AppNameBody) -> dict:
        return await _service_client.app_info(body.app_name)

    @app.post("/cuactl/app-position")
    async def http_app_position(body: AppNameBody) -> dict:
        return await _service_client.app_position(body.app_name)

    @app.post("/cuactl/open-app")
    async def http_open_app(body: AppNameBody) -> dict:
        return await _service_client.open_app(body.app_name)

    @app.post("/cuactl/close-app")
    async def http_close_app(body: AppNameBody) -> dict:
        return await _service_client.close_app(body.app_name)

    @app.get("/")
    async def root() -> dict:
        return {
            "service": "cuactl-relay",
            "version": "2.0.0",
            "endpoints": "see /docs",
        }

except ImportError:
    # fastapi/uvicorn not installed — CLI mode only.
    app = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# CLI entry point (legacy / host debugging)
# ---------------------------------------------------------------------------

import asyncio


def _print_result(result: dict):
    """Print result as JSON."""
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def _main():
    if len(sys.argv) < 2:
        print("Usage: cuactl <command> [args...]", file=sys.stderr)
        print("Commands: capture, click, move, scroll, drag, type, press_key,", file=sys.stderr)
        print("          list-apps, list-installed-apps, app-info, app-position,", file=sys.stderr)
        print("          open-app, close-app, screen-size", file=sys.stderr)
        print("", file=sys.stderr)
        print("HTTP mode: uvicorn relay_server:app --host 0.0.0.0 --port 8000", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    client = CuaClient()

    try:
        if cmd == "capture":
            _print_result(await client.capture())
        elif cmd == "screen-size":
            _print_result(await client.screen_size())
        elif cmd == "click":
            x, y = int(sys.argv[2]), int(sys.argv[3])
            btn = sys.argv[4] if len(sys.argv) > 4 else "left"
            _print_result(await client.click(x, y, btn))
        elif cmd == "move":
            x, y = int(sys.argv[2]), int(sys.argv[3])
            _print_result(await client.move(x, y))
        elif cmd == "scroll":
            dx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
            dy = int(sys.argv[3]) if len(sys.argv) > 3 else 0
            _print_result(await client.scroll(dx, dy))
        elif cmd == "drag":
            fx, fy, tx, ty = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
            _print_result(await client.drag(fx, fy, tx, ty))
        elif cmd == "type":
            text = " ".join(sys.argv[2:])
            _print_result(await client.type_text(text))
        elif cmd == "press_key":
            key = sys.argv[2]
            _print_result(await client.press_key(key))
        elif cmd == "list-apps":
            _print_result(await client.list_apps())
        elif cmd == "list-installed-apps":
            _print_result(await client.list_installed_apps())
        elif cmd == "app-info":
            _print_result(await client.app_info(sys.argv[2]))
        elif cmd == "app-position":
            _print_result(await client.app_position(sys.argv[2]))
        elif cmd == "open-app":
            _print_result(await client.open_app(sys.argv[2]))
        elif cmd == "close-app":
            _print_result(await client.close_app(sys.argv[2]))
        else:
            print(f"Unknown command: {cmd}", file=sys.stderr)
            sys.exit(1)
    finally:
        await client.close()


def main():
    asyncio.run(_main())


if __name__ == "__main__":
    main()
