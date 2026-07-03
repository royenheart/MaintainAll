"""Permission control for CUA Control Plane.

Two-layer permission model:
  Layer 1 (preset):   permission_level (off/readonly/full/strict) — coarse mode,
                       backwards-compatible. Acts as a preset that expands to an
                       operation set when allowed_operations is empty.
  Layer 2 (fine):     allowed_operations — explicit per-operation whitelist.
                       When non-empty, takes precedence over the preset.
  Layer 3 (spatial):  region_restriction — coordinate-based ops (click/move/scroll/
                       drag) are only allowed within the configured rectangle.
  Layer 4 (app):      allowed_apps — coordinate-based ops are only allowed when the
                       window at the target point belongs to an allowed app.

check_permission(operation)         — checks layers 1+2 (operation-level)
check_spatial_permission(operation, x, y) — additionally checks layers 3+4
"""

from __future__ import annotations

import enum
import functools
import logging
from typing import Callable, Optional

from .config import get_config

logger = logging.getLogger(__name__)


class PermissionLevel(str, enum.Enum):
    OFF = "off"
    READONLY = "readonly"
    FULL = "full"
    STRICT = "strict"


# Full operation taxonomy. These are the toggleable operations in /settings.
ALL_OPS = frozenset({
    # Read-only operations
    "capture",
    "list_apps",
    "app_info",
    "app_position",
    "health",
    "screen_size",
    # Write operations — coordinate-based (subject to region/app checks)
    "click",
    "doubleclick",
    "type",
    "press_key",
    "move",
    "scroll",
    "drag",
    # Write operations — app-level (not coordinate-based)
    "open_app",
    "close_app",
    "start_app",
})

READ_OPS = frozenset({
    "capture", "list_apps", "app_info", "app_position", "health", "screen_size",
})

WRITE_OPS = frozenset({
    "click", "doubleclick", "type", "press_key", "move", "scroll", "drag",
    "open_app", "close_app", "start_app",
})

# Coordinate-based operations that are subject to region_restriction and
# allowed_apps checks (in addition to the operation whitelist).
COORD_OPS = frozenset({
    "click", "doubleclick", "move", "scroll", "drag",
})

# Preset → operation set mapping. Selecting a preset sets allowed_operations
# to the corresponding set. "custom" means allowed_operations is user-defined.
PRESETS: dict[str, frozenset[str]] = {
    "off": frozenset(),
    "readonly": READ_OPS,
    "full": ALL_OPS,
    # strict = full but with interactive confirmation (handled at API layer)
    "strict": ALL_OPS,
}


class AccessDeniedError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _resolve_allowed_operations() -> frozenset[str]:
    """Resolve the effective allowed-operations set.

    Precedence:
      1. If cfg.allowed_operations is non-empty → use it directly (custom mode).
      2. Else → expand cfg.permission_level via PRESETS.
    """
    cfg = get_config()
    if cfg.allowed_operations:
        return frozenset(cfg.allowed_operations)
    preset = PRESETS.get(cfg.permission_level, PRESETS["full"])
    return preset


def check_permission(operation: str) -> None:
    """Check if the given operation is allowed (layers 1+2).

    Raises AccessDeniedError if not permitted.
    Does NOT check spatial/app restrictions — use check_spatial_permission
    for coordinate-based operations.
    """
    cfg = get_config()
    level = PermissionLevel(cfg.permission_level) if cfg.permission_level in PRESETS else PermissionLevel.FULL

    if level == PermissionLevel.OFF and not cfg.allowed_operations:
        raise AccessDeniedError(
            "Computer Use is currently disabled. "
            "Enable it via the system tray icon or /settings page."
        )

    allowed = _resolve_allowed_operations()
    if operation not in allowed:
        raise AccessDeniedError(
            f"Operation '{operation}' is not allowed. "
            f"Allowed operations: {sorted(allowed) or '(none)'}. "
            "Adjust the operation whitelist in /settings."
        )

    # STRICT mode — write ops would require interactive confirmation
    # (implemented in the API layer via a pending-confirmation queue)
    if level == PermissionLevel.STRICT and operation in WRITE_OPS:
        # For now, strict = full in automated mode
        pass


def check_spatial_permission(operation: str, x: Optional[int] = None, y: Optional[int] = None) -> None:
    """Check operation + spatial (region + app) permissions.

    For coordinate-based operations (click/move/scroll/drag), additionally
    verifies that (x, y) falls within region_restriction (if configured) and
    that the app at (x, y) is in allowed_apps (if configured).

    For non-coordinate operations, only check_permission is applied.
    """
    # Layer 1+2: operation whitelist
    check_permission(operation)

    # Layers 3+4: only for coordinate-based ops with coordinates provided
    if operation not in COORD_OPS or x is None or y is None:
        return

    cfg = get_config()

    # Layer 3: region restriction
    region = cfg.region_restriction
    if region:
        rx = region.get("x", 0)
        ry = region.get("y", 0)
        rw = region.get("width", 0)
        rh = region.get("height", 0)
        if not (rx <= x < rx + rw and ry <= y < ry + rh):
            raise AccessDeniedError(
                f"Coordinates ({x}, {y}) are outside the allowed region "
                f"({rx},{ry})-({rx+rw},{ry+rh}). "
                "Adjust region_restriction in /settings."
            )

    # Layer 4: app restriction
    if cfg.allowed_apps:
        app_name = _resolve_app_at_point(x, y)
        if app_name is None:
            raise AccessDeniedError(
                f"No application window found at ({x}, {y}). "
                "Cannot verify app allowlist."
            )
        if not _app_matches_allowlist(app_name, cfg.allowed_apps):
            raise AccessDeniedError(
                f"Application '{app_name}' at ({x}, {y}) is not in the allowed list. "
                f"Allowed apps: {cfg.allowed_apps}. "
                "Adjust allowed_apps in /settings."
            )


def _resolve_app_at_point(x: int, y: int) -> Optional[str]:
    """Resolve which application's window contains the point (x, y).

    Tries cua-driver's accessibility tree first (via cua_core._find_window_at_point),
    falls back to deterministic_ops window enumeration.
    Returns the process name (lowercased) or window title, or None if not found.
    """
    try:
        from .cua_core import resolve_app_at_point
        return resolve_app_at_point(x, y)
    except Exception as e:
        logger.debug("resolve_app_at_point via cua_core failed: %s", e)
    return None


def _app_matches_allowlist(app_name: str, allowlist: list[str]) -> bool:
    """Check if app_name matches any entry in the allowlist (case-insensitive substring)."""
    app_lower = app_name.lower()
    for allowed in allowlist:
        if allowed.lower() in app_lower or app_lower in allowed.lower():
            return True
    return False


def requires_permission(operation: str):
    """Decorator that checks operation-level permission before executing.

    For coordinate-based operations, prefer calling check_spatial_permission
    directly in the endpoint handler (since x/y come from the request body).
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            check_permission(operation)
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def get_allowed_ops() -> dict:
    """Return the effective allowed operations for health/status reporting."""
    cfg = get_config()
    allowed = _resolve_allowed_operations()
    # Determine the "mode" label for display
    if cfg.allowed_operations:
        mode = "custom"
    else:
        mode = cfg.permission_level
    return {
        "permission_level": mode,
        "preset": cfg.permission_level,
        "allowed_operations": sorted(allowed),
        "region_restriction": cfg.region_restriction,
        "allowed_apps": cfg.allowed_apps,
    }
