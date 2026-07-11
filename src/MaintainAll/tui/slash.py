"""Slash-command registry: decorate handlers once; /help reads the same metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SlashCommand:
    name: str
    summary: str
    usage: str
    method: str


_REGISTRY: dict[str, SlashCommand] = {}


def slash_command(
    name: str,
    summary: str,
    usage: str = "",
) -> Callable[[Callable], Callable]:
    """Register a MaintainAllApp method as a slash command.

    ``usage`` defaults to ``/{name}``. ``summary`` is what ``/help`` prints.
    """

    def decorator(fn: Callable) -> Callable:
        key = name.strip().lstrip("/").lower()
        _REGISTRY[key] = SlashCommand(
            name=key,
            summary=summary.strip(),
            usage=(usage or f"/{key}").strip(),
            method=fn.__name__,
        )
        return fn

    return decorator


def registered_commands() -> list[SlashCommand]:
    return sorted(_REGISTRY.values(), key=lambda c: c.name)


def get_command(name: str) -> SlashCommand | None:
    return _REGISTRY.get(name.strip().lstrip("/").lower())


def format_help_lines() -> list[str]:
    lines = ["Available commands:"]
    for cmd in registered_commands():
        lines.append(f"  {cmd.usage}")
        lines.append(f"      {cmd.summary}")
    return lines


def completion_strings() -> list[str]:
    """Slash prefixes for grey inline completion (``/run`` keeps trailing space)."""
    out: list[str] = []
    for cmd in registered_commands():
        if cmd.name == "run":
            out.append("/run ")
        else:
            out.append(f"/{cmd.name}")
    return out
