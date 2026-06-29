"""CUA (Computer Use Agent) core wrapper.

Provides screen capture, mouse, keyboard, and clipboard operations
through the CUA sandbox/driver.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lazy-loaded CUA sandbox instance
_sandbox: Any = None
_sandbox_cm: Any = None
_cua_available: bool | None = None


def _check_cua_available() -> bool:
    """Check if the CUA package is installed."""
    global _cua_available
    if _cua_available is None:
        try:
            import cua  # noqa: F401
            _cua_available = True
        except ImportError:
            logger.warning(
                "CUA package not installed. Install with: pip install cua"
            )
            _cua_available = False
    return _cua_available


async def _ensure_sandbox() -> Any:
    """Ensure CUA sandbox is initialized. Creates one if needed."""
    global _sandbox, _sandbox_cm

    if _sandbox is not None:
        try:
            # Quick health check
            await _sandbox.shell.exec("echo ok", timeout=5)
            return _sandbox
        except Exception:
            logger.warning("CUA sandbox connection lost, recreating...")
            await _cleanup_sandbox()

    if not _check_cua_available():
        raise RuntimeError(
            "CUA package is not installed. "
            "Install with: pip install cua"
        )

    from cua import Sandbox, Image

    logger.info("Starting CUA sandbox...")
    sandbox_cm = Sandbox.ephemeral(Image.linux(), local=True)
    sandbox = await sandbox_cm.__aenter__()

    _sandbox = sandbox
    _sandbox_cm = sandbox_cm
    logger.info("CUA sandbox ready")
    return sandbox


async def _cleanup_sandbox() -> None:
    global _sandbox, _sandbox_cm
    if _sandbox_cm is not None:
        try:
            await _sandbox_cm.__aexit__(None, None, None)
        except Exception as e:
            logger.warning("Error closing CUA sandbox: %s", e)
    _sandbox = None
    _sandbox_cm = None


async def capture() -> dict:
    """Take a screenshot. Returns {success, base64, mime_type}."""
    sandbox = await _ensure_sandbox()
    try:
        screenshot = await sandbox.screenshot()
        raw = await _extract_screenshot_data(screenshot)
        return {
            "success": True,
            "base64": raw,
            "mime_type": "image/png",
        }
    except Exception as e:
        logger.error("capture failed: %s", e)
        return {"success": False, "error": str(e)}


async def _extract_screenshot_data(screenshot: Any) -> str:
    """Extract base64 data from various CUA screenshot return types."""
    if isinstance(screenshot, str):
        if screenshot.startswith("data:image"):
            return screenshot.split(",", 1)[1]
        return screenshot
    if isinstance(screenshot, (bytes, bytearray)):
        return base64.b64encode(bytes(screenshot)).decode()
    if hasattr(screenshot, "save"):
        import io
        buf = io.BytesIO()
        screenshot.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    payload = {}
    if hasattr(screenshot, "model_dump"):
        payload = screenshot.model_dump()
    elif isinstance(screenshot, dict):
        payload = screenshot
    for key in ("data", "base64", "image"):
        if key in payload:
            return await _extract_screenshot_data(payload[key])
    return str(screenshot)


async def click(x: int, y: int, button: str = "left") -> dict:
    """Click at screen coordinates."""
    sandbox = await _ensure_sandbox()
    try:
        await sandbox.mouse.click(x, y, button=button)
        return {"success": True, "x": x, "y": y, "button": button}
    except Exception as e:
        logger.error("click(%d,%d) failed: %s", x, y, e)
        return {"success": False, "error": str(e)}


async def move(x: int, y: int) -> dict:
    """Move mouse to coordinates."""
    sandbox = await _ensure_sandbox()
    try:
        await sandbox.mouse.move(x, y)
        return {"success": True, "x": x, "y": y}
    except Exception as e:
        logger.error("move(%d,%d) failed: %s", x, y, e)
        return {"success": False, "error": str(e)}


async def scroll(dx: int = 0, dy: int = 0) -> dict:
    """Scroll mouse wheel."""
    sandbox = await _ensure_sandbox()
    try:
        # CUA provides mouse.scroll or mouse.wheel
        if hasattr(sandbox.mouse, "scroll"):
            await sandbox.mouse.scroll(dx, dy)
        elif hasattr(sandbox.mouse, "wheel"):
            await sandbox.mouse.wheel(dx, dy)
        else:
            return {"success": False, "error": "scroll/wheel not supported by CUA sandbox"}
        return {"success": True, "dx": dx, "dy": dy}
    except Exception as e:
        logger.error("scroll failed: %s", e)
        return {"success": False, "error": str(e)}


async def drag(from_x: int, from_y: int, to_x: int, to_y: int) -> dict:
    """Drag from one coordinate to another."""
    sandbox = await _ensure_sandbox()
    try:
        if hasattr(sandbox.mouse, "drag"):
            await sandbox.mouse.drag(from_x, from_y, to_x, to_y)
        else:
            # Fallback: move + press + move + release
            await sandbox.mouse.move(from_x, from_y)
            await sandbox.mouse.down()
            await sandbox.mouse.move(to_x, to_y)
            await sandbox.mouse.up()
        return {"success": True, "from": [from_x, from_y], "to": [to_x, to_y]}
    except Exception as e:
        logger.error("drag failed: %s", e)
        return {"success": False, "error": str(e)}


async def type_text(text: str) -> dict:
    """Type text using keyboard."""
    sandbox = await _ensure_sandbox()
    try:
        await sandbox.keyboard.type(text)
        return {"success": True, "text": text}
    except Exception as e:
        logger.error("type_text failed: %s", e)
        return {"success": False, "error": str(e)}


async def press_key(key: str) -> dict:
    """Press a keyboard key."""
    sandbox = await _ensure_sandbox()
    try:
        await sandbox.keyboard.press(key)
        return {"success": True, "key": key}
    except Exception as e:
        logger.error("press_key(%s) failed: %s", key, e)
        return {"success": False, "error": str(e)}


async def screen_size() -> dict:
    """Get screen dimensions."""
    sandbox = await _ensure_sandbox()
    try:
        screenshot = await sandbox.screenshot()
        # Try to get dimensions from the screenshot object
        if hasattr(screenshot, "width") and hasattr(screenshot, "height"):
            return {"success": True, "width": screenshot.width, "height": screenshot.height}
        # Fallback: decode PNG header
        import struct
        raw = await _extract_screenshot_data(screenshot)
        data = base64.b64decode(raw)
        # Parse PNG IHDR: width is at offset 16, height at offset 20
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            w, h = struct.unpack('>II', data[16:24])
            return {"success": True, "width": w, "height": h}
        return {"success": False, "error": "Cannot determine screen size"}
    except Exception as e:
        logger.error("screen_size failed: %s", e)
        return {"success": False, "error": str(e)}


async def shutdown() -> None:
    """Clean up CUA sandbox resources."""
    await _cleanup_sandbox()
