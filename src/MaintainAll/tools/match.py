from __future__ import annotations

import re
import shlex
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from MaintainAll.missions.models import AllowedCommand

_SHELLS = frozenset({"bash", "sh", "zsh", "fish"})


class CommandGate:
    def __init__(self, allowed: list[AllowedCommand]) -> None:
        self._allowed = allowed
        self.counts: dict[str, int] = {}
        self._last_match: AllowedCommand | None = None

    @property
    def last_match(self) -> AllowedCommand | None:
        return self._last_match

    def resolve(self, cmd: str) -> AllowedCommand | None:
        tokens = shlex.split(cmd)
        if not tokens:
            return None

        first = tokens[0]
        matched: AllowedCommand | None = None
        for allowed in self._allowed:
            if re.fullmatch(allowed.pattern, cmd):
                matched = allowed
                break

        if first in _SHELLS and matched is None:
            return None
        return matched

    def check(self, cmd: str) -> bool:
        matched = self.resolve(cmd)
        self._last_match = matched
        if matched is None:
            return False
        self.counts[matched.pattern] = self.counts.get(matched.pattern, 0) + 1
        return True


class UnlimitedGate:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self._last_match: AllowedCommand | None = None

    @property
    def last_match(self) -> AllowedCommand | None:
        return self._last_match

    def check(self, cmd: str) -> bool:
        if not cmd.strip():
            return False
        from MaintainAll.missions.models import AllowedCommand

        self._last_match = AllowedCommand(pattern="*", cwd=".")
        self.counts["*"] = self.counts.get("*", 0) + 1
        return True
