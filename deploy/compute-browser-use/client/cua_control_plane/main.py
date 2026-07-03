"""Main entry point for CUA Control Plane.

Starts:
1. FastAPI REST server on configured port
2. System tray icon for control

Usage:
    python -m cua_control_plane.main
    python -m cua_control_plane.main --host 0.0.0.0 --port 9110
"""

from __future__ import annotations

import sys
import io
import os

if sys.stderr is None:
    sys.stderr = io.TextIOWrapper(open(os.devnull, 'w'))
if sys.stdout is None:
    sys.stdout = io.TextIOWrapper(open(os.devnull, 'w'))

# Enable per-monitor DPI awareness as early as possible.
# Without this, Win32 APIs (GetSystemMetrics, EnumDisplayMonitors,
# GetMonitorInfoW) return LOGICAL pixels (scaled by DPI factor), while
# PIL.ImageGrab returns PHYSICAL pixels. This mismatch breaks screen
# coordinate mapping (click positions, region overlays, screenshots)
# on multi-monitor setups where one monitor has DPI scaling (e.g. 200%).
# With DPI awareness, both Win32 and PIL return physical pixels consistently.
if os.name == "nt":
    try:
        ctypes = __import__("ctypes")
        user32 = ctypes.windll.user32
        _dpi_set = False
        # Method 1: SetProcessDpiAwarenessContext (Win10 1607+)
        # PER_MONITOR_AWARE_V2 = -4. This handle is passed as a pointer-sized
        # integer, so we must set argtypes/restype correctly (default c_int
        # truncates on 64-bit, causing failure).
        try:
            user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
            if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                _dpi_set = True
        except (AttributeError, OSError, ValueError):
            pass
        # Method 2: SetProcessDpiAwareness (Win 8.1+), PER_MONITOR_AWARE = 2
        if not _dpi_set:
            try:
                hresult = ctypes.windll.shcore.SetProcessDpiAwareness(2)
                if hresult == 0:  # S_OK
                    _dpi_set = True
            except (AttributeError, OSError):
                pass
        # Method 3: SetProcessDPIAware (Vista+), system DPI aware (fallback)
        if not _dpi_set:
            try:
                if user32.SetProcessDPIAware():
                    _dpi_set = True
            except (AttributeError, OSError):
                pass
    except Exception:
        pass  # Non-Windows or API unavailable — logical = physical anyway

import argparse
import asyncio
import logging
from pathlib import Path

import uvicorn

from .config import get_config, reload_config
from .tray import ControlPlaneTray


def setup_logging(config):
    """Configure logging to file and console."""
    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_dir / "cua_control_plane.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if sys.stderr is not None:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        root.addHandler(ch)

    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def main():
    parser = argparse.ArgumentParser(description="CUA Control Plane")
    parser.add_argument("--host", help="API bind host", default=None)
    parser.add_argument("--port", type=int, help="API bind port", default=None)
    parser.add_argument("--no-tray", action="store_true", help="Disable system tray")
    args = parser.parse_args()

    config = get_config()
    setup_logging(config)

    logger = logging.getLogger(__name__)
    host = args.host or config.api_host
    port = args.port or config.api_port

    uvicorn_config = uvicorn.Config(
        "cua_control_plane.api:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )
    server = uvicorn.Server(uvicorn_config)

    from .cua_core import start_daemon
    start_daemon()

    loop = asyncio.get_running_loop()
    tray = ControlPlaneTray(loop, server=server)
    if not args.no_tray:
        tray.start()

    logger.info("=" * 60)
    logger.info("CUA Control Plane v0.1.0")
    logger.info("API server: http://%s:%d", host, port)
    logger.info("Health check: http://%s:%d/health", host, port)
    logger.info("Permission: %s", get_config().permission_level.upper())
    logger.info("=" * 60)

    try:
        await server.serve()
    except asyncio.CancelledError:
        pass
    finally:
        tray.stop()
        logger.info("CUA Control Plane stopped")


if __name__ == "__main__":
    asyncio.run(main())
