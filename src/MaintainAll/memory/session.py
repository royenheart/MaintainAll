from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from MaintainAll.missions.models import Mission


@dataclass
class SessionMemory:
    messages: list[dict] = field(default_factory=list)
    mission: Mission | None = None
    command_counts: dict[str, int] = field(default_factory=dict)
    last_report: Path | None = None
    assess_notes: str = ""
    mode: str = "readonly"

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def clear(self) -> None:
        self.messages.clear()
        self.mission = None
        self.command_counts.clear()
        self.last_report = None
        self.assess_notes = ""
        self.mode = "readonly"
