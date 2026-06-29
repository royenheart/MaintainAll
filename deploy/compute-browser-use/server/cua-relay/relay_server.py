"""CUA Relay — Bridges Hermes Agent to the remote Client Control Plane.

Exposes a `cuactl` CLI that Hermes Agent's computer_use tool calls.
Each command translates to an HTTP request to the remote Client Control Plane.

Usage:
    cuactl capture
    cuactl click 100 200
    cuactl list-apps

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
                timeout=httpx.Timeout(60.0),
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
            # Write to temp file for Hermes to pick up
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
# CLI entry point
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
