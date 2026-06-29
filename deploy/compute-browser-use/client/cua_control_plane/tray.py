"""Windows system tray for CUA Control Plane.

Provides:
- Status indicator (connected/disconnected)
- Permission level switching (off/readonly/full/strict)
- Open config
- Quit
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False
    logger.warning("pystray or Pillow not installed. Tray icon disabled.")


def _create_icon_image(color: str = "green") -> Image.Image:
    """Create a simple colored circle icon for the tray."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    colors = {
        "green": (0, 200, 100),
        "yellow": (255, 200, 0),
        "red": (220, 50, 50),
        "gray": (128, 128, 128),
    }
    rgb = colors.get(color, colors["gray"])
    draw.ellipse([8, 8, size - 8, size - 8], fill=rgb)
    return img


class ControlPlaneTray:
    """System tray controller."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self._tray: Optional[pystray.Icon] = None
        self._running = False

    def _build_menu(self):
        from .config import get_config, reload_config
        cfg = get_config()

        def _set_permission(level: str):
            def _inner(icon, item):
                cfg.permission_level = level
                cfg.save()
                # Update all menu items
                icon.update_menu()
            return _inner

        # Dynamic menu based on current permission
        def _make_perm_item(label: str, level: str) -> pystray.MenuItem:
            checked = cfg.permission_level == level
            return pystray.MenuItem(
                label,
                _set_permission(level),
                checked=lambda item, lvl=level: cfg.permission_level == lvl,
                radio=True,
            )

        def _quit(icon, item):
            icon.stop()
            self._running = False
            # Schedule shutdown
            self.loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._shutdown())
            )

        return pystray.Menu(
            pystray.MenuItem(
                f"Status: {cfg.permission_level.upper()}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            _make_perm_item("🔴 Off (Deny All)", "off"),
            _make_perm_item("🟡 Readonly (View Only)", "readonly"),
            _make_perm_item("🟢 Full Access", "full"),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", _quit),
        )

    async def _shutdown(self):
        """Shutdown cleanup."""
        from .cua_core import shutdown as cua_shutdown
        await cua_shutdown()

    def _run_tray(self):
        """Run tray in dedicated thread."""
        if not HAS_TRAY:
            return

        icon = _create_icon_image("green")
        self._tray = pystray.Icon(
            "cua_control_plane",
            icon,
            "CUA Control Plane",
            menu=self._build_menu(),
        )
        self._running = True
        self._tray.run()

    def start(self):
        """Start tray in background thread."""
        if not HAS_TRAY:
            logger.info("Tray icon not available (pystray/Pillow not installed)")
            return

        thread = threading.Thread(target=self._run_tray, daemon=True)
        thread.start()
        logger.info("System tray started")

    def stop(self):
        if self._tray and self._running:
            self._tray.stop()
            self._running = False

    def update_icon(self, color: str):
        """Update tray icon color."""
        if self._tray and HAS_TRAY:
            self._tray.icon = _create_icon_image(color)
