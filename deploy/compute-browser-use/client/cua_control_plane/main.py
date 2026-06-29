"""Main entry point for CUA Control Plane.

Starts:
1. FastAPI REST server on configured port
2. System tray icon for control

Usage:
    python -m cua_control_plane.main
    python -m cua_control_plane.main --host 0.0.0.0 --port 9110
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
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

    # File handler
    fh = logging.FileHandler(log_dir / "cua_control_plane.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(fh)
    root.addHandler(ch)

    # Quiet noisy libs
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

    # Start system tray
    loop = asyncio.get_running_loop()
    tray = ControlPlaneTray(loop)
    if not args.no_tray:
        tray.start()

    # Configure uvicorn
    config = uvicorn.Config(
        "cua_control_plane.api:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )
    server = uvicorn.Server(config)

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
