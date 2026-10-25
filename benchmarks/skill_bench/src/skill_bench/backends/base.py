"""Thin execution boundary; evaluators and experiment budgets stay outside it."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


Emit = Callable[[dict], None]


@dataclass
class PreparedTrial:
    spec: dict
    output: Path
    workspace: Path
    prompts: list[str]
    attachments: list[list[Path]]
    assets: dict = field(default_factory=dict)
    skill_hash: str | None = None
    state: dict = field(default_factory=dict)


class Backend(ABC):
    """A backend cannot silently substitute another backend or retry a call."""

    id: str
    capabilities: dict

    @abstractmethod
    def doctor(self, config: dict) -> dict:
        """Probe enforcement without a model request."""

    @abstractmethod
    def prepare(self, spec: dict, output: Path) -> PreparedTrial:
        """Stage explicit solver inputs; never stage the complete case card."""

    @abstractmethod
    def execute(self, prepared: PreparedTrial, emit: Emit) -> dict:
        """Reserve each call through emit before launching the trusted client."""

    def collect(self, prepared: PreparedTrial, execution: dict) -> dict:
        """Return private snapshots and telemetry, without assigning quality."""
        return execution

    def execute_trial(self, spec: dict, output: Path, emit: Emit) -> dict:
        prepared = self.prepare(spec, output)
        return self.collect(prepared, self.execute(prepared, emit))
