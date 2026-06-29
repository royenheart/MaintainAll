"""Permission control for CUA Control Plane.

Enforces read/write access based on permission_level config:
- off:       deny all
- readonly:  allow capture + deterministic read ops only
- full:      allow all operations
- strict:    allow all, but write ops require interactive confirmation (per-session)
"""

from __future__ import annotations

import enum
import functools
import logging
from typing import Callable

from .config import get_config

logger = logging.getLogger(__name__)


class PermissionLevel(str, enum.Enum):
    OFF = "off"
    READONLY = "readonly"
    FULL = "full"
    STRICT = "strict"


READ_OPS = frozenset({
    "capture",
    "list_apps",
    "app_info",
    "app_position",
    "health",
})

WRITE_OPS = frozenset({
    "click",
    "type",
    "press_key",
    "move",
    "scroll",
    "drag",
    "open_app",
    "close_app",
    "start_app",
})


class AccessDeniedError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def check_permission(operation: str) -> None:
    """Check if current permission level allows the given operation.

    Raises AccessDeniedError if not permitted.
    """
    cfg = get_config()
    level = PermissionLevel(cfg.permission_level)

    if level == PermissionLevel.OFF:
        raise AccessDeniedError(
            "Computer Use is currently disabled. "
            "Enable it via the system tray icon."
        )

    if level == PermissionLevel.READONLY and operation in WRITE_OPS:
        raise AccessDeniedError(
            f"Operation '{operation}' requires write access. "
            "Current permission level is 'readonly'. "
            "Switch to 'full' via the system tray icon."
        )

    # STRICT mode — write ops would require interactive confirmation
    # (implemented in the API layer via a pending-confirmation queue)
    if level == PermissionLevel.STRICT and operation in WRITE_OPS:
        # For now, strict = full in automated mode
        # Interactive confirmation requires tray integration
        pass


def requires_permission(operation: str):
    """Decorator that checks permission before executing."""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            check_permission(operation)
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def get_allowed_ops() -> dict:
    """Return the set of currently allowed operations for health reporting."""
    cfg = get_config()
    level = PermissionLevel(cfg.permission_level)

    allowed = set()
    if level == PermissionLevel.OFF:
        pass  # nothing allowed
    elif level == PermissionLevel.READONLY:
        allowed = set(READ_OPS)
    elif level in (PermissionLevel.FULL, PermissionLevel.STRICT):
        allowed = set(READ_OPS) | set(WRITE_OPS)

    return {
        "permission_level": level.value,
        "allowed_operations": sorted(allowed),
    }
