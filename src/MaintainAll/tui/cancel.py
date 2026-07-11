"""Double-Esc arming for cancelling an active agent session."""

from __future__ import annotations

from time import monotonic
from typing import Literal

ArmResult = Literal["armed", "confirm"]


class SessionCancelArm:
    """First Esc arms; second Esc within ``window_s`` confirms cancel."""

    def __init__(self, *, window_s: float = 2.0) -> None:
        self.window_s = window_s
        self._armed_until = 0.0

    def clear(self) -> None:
        self._armed_until = 0.0

    @property
    def is_armed(self) -> bool:
        return monotonic() <= self._armed_until

    def press(self, *, now: float | None = None) -> ArmResult:
        t = monotonic() if now is None else now
        if t <= self._armed_until:
            self._armed_until = 0.0
            return "confirm"
        self._armed_until = t + self.window_s
        return "armed"
