from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Expect:
    type: str  # contains | report_section | file_exists
    patterns: list[str] = field(default_factory=list)
    name: str | None = None
    path_glob: str | None = None


@dataclass
class AllowedCommand:
    pattern: str
    cwd: str = "."


@dataclass
class TaskNode:
    id: str
    name: str
    needs: list[str]
    instruction: str
    expect: Expect
    script: str | None = None
    tasks: list[TaskNode] = field(default_factory=list)
    status: str = "pending"  # runtime, not persisted


@dataclass
class NotifyConfig:
    on_complete: bool = True
    on_failure: bool = True


@dataclass
class Mission:
    id: str
    name: str
    description: str
    skills: list[str]
    schedule: str | None
    notify: NotifyConfig
    allowed_commands: list[AllowedCommand]
    tasks: list[TaskNode]
