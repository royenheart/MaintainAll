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

    def __init__(self, loop: asyncio.AbstractEventLoop, server=None):
        self.loop = loop
        self._server = server
        self._tray: Optional[pystray.Icon] = None
        self._running = False

    def _build_screen_menu(self):
        from .config import get_config
        from .screens import get_screens

        cfg = get_config()
        screens = get_screens()
        allowed = cfg.allowed_screens or []

        def _toggle_all(icon, item):
            cfg.allowed_screens = []
            cfg.save()
            icon._menu = self._build_menu()
            icon.update_menu()

        def _make_screen_toggle(idx: int):
            def _inner(icon, item):
                if not cfg.allowed_screens:
                    cfg.allowed_screens = [s["index"] for s in screens if s["index"] != idx]
                elif idx in cfg.allowed_screens:
                    cfg.allowed_screens.remove(idx)
                else:
                    cfg.allowed_screens.append(idx)
                cfg.save()
                icon._menu = self._build_menu()
                icon.update_menu()
            return _inner

        items = [
            pystray.MenuItem(
                "All Screens",
                _toggle_all,
                checked=lambda item: not allowed,
            ),
            pystray.Menu.SEPARATOR,
        ]
        for s in screens:
            name = s["name"].rstrip("\x00") if "\x00" in s["name"] else s["name"]
            items.append(pystray.MenuItem(
                f"{name}  {s['width']}x{s['height']}",
                _make_screen_toggle(s["index"]),
                checked=lambda item, idx=s["index"]: idx in (cfg.allowed_screens or []),
            ))

        return pystray.Menu(*items)

    def _build_menu(self):
        from .config import get_config, reload_config
        cfg = get_config()

        def _set_permission(level: str):
            def _inner(icon, item):
                cfg.permission_level = level
                cfg.save()
                icon._menu = self._build_menu()
                icon.update_menu()
            return _inner

        def _set_control_mode(mode: str):
            def _inner(icon, item):
                cfg.control_mode = mode
                cfg.save()
                icon._menu = self._build_menu()
                icon.update_menu()
            return _inner

        def _make_perm_item(label: str, level: str) -> pystray.MenuItem:
            return pystray.MenuItem(
                label,
                _set_permission(level),
                checked=lambda item, lvl=level: cfg.permission_level == lvl,
                radio=True,
            )

        def _quit(icon, item):
            self.loop.call_soon_threadsafe(self._shutdown_all)
            icon.stop()
            self._running = False

        screen_count = "1 screen"
        try:
            from .screens import get_screens
            sc = get_screens()
            screen_count = f"{len(sc)} screens"
        except Exception:
            pass

        cua_ok = False
        uia_ok = False
        try:
            from .cua_core import check_cua_available, check_uia_available
            cua_ok = check_cua_available()
            if cua_ok:
                uia_ok = check_uia_available()
        except Exception:
            pass

        def _enable_uia(icon, item):
            import subprocess, os
            binary = None
            candidates = [
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Cua", "cua-driver", "bin", "cua-driver.exe"),
            ]
            for p in candidates:
                if p and os.path.isfile(p):
                    binary = p
                    break
            if not binary:
                return
            try:
                no_window = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command",
                     f"Start-Process '{binary}' -ArgumentList 'autostart','kick' -Verb RunAs -WindowStyle Hidden -Wait"],
                    shell=False,
                    creationflags=no_window,
                )
            except Exception:
                pass

        mode = cfg.control_mode
        mode_label = "Solo" if mode == "solo" else "Collaborative"
        driver_label = "cua-driver" if cua_ok else "native"
        uia_label = "UIAccess ON" if uia_ok else "UIAccess OFF"

        def _open_settings(icon, item):
            """Open the /settings web UI in the default browser."""
            import webbrowser
            from .config import get_config as _get_cfg
            cfg = _get_cfg()
            host = cfg.api_host or "127.0.0.1"
            port = cfg.api_port or 9111
            url = f"http://{host}:{port}/settings"
            try:
                webbrowser.open(url)
            except Exception:
                pass

        items = [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                f"Permission: {cfg.permission_level.upper()}  |  {driver_label}  |  {uia_label}",
                None,
                enabled=False,
            ),
        ]

        collaborative_checked = cfg.control_mode == "collaborative"
        solo_checked = cfg.control_mode == "solo"

        items += [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                f"Mode: {mode_label}",
                pystray.Menu(
                    pystray.MenuItem(
                        "Collaborative (non-intrusive)",
                        _set_control_mode("collaborative"),
                        checked=lambda item: cfg.control_mode == "collaborative",
                        radio=True,
                    ),
                    pystray.MenuItem(
                        "Solo (full control)",
                        _set_control_mode("solo"),
                        checked=lambda item: cfg.control_mode == "solo",
                        radio=True,
                    ),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                f"Screen Access ({screen_count})",
                self._build_screen_menu(),
            ),
        ]
        if not uia_ok and cua_ok:
            items.append(pystray.MenuItem(
                "Enable UIAccess (admin required)",
                _enable_uia,
            ))
            items.append(pystray.Menu.SEPARATOR)
        items += [
            pystray.MenuItem("Open Settings...", _open_settings),
            pystray.Menu.SEPARATOR,
            _make_perm_item("Off (Deny All)", "off"),
            _make_perm_item("Readonly (View Only)", "readonly"),
            _make_perm_item("Full Access", "full"),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", _quit),
        ]
        return pystray.Menu(*items)

    def _shutdown_all(self):
        """Shutdown uvicorn server and cleanup CUA sandbox."""
        import asyncio as _asyncio
        task = _asyncio.ensure_future(self._shutdown())
        self._server.should_exit = True

    async def _shutdown(self):
        """Cleanup CUA sandbox resources."""
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
