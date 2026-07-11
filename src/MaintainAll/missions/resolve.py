from __future__ import annotations

import os
import re

from MaintainAll.missions.models import Mission

_RUN_RE = re.compile(r"^/run(?:\s+(.*))?$", re.IGNORECASE)
_RUN_PREFIX_RE = re.compile(r"^/r(?:u(?:n)?)?$", re.IGNORECASE)


def parse_run_command(text: str) -> str | None:
    """If ``text`` is a ``/run`` command, return the mission query (may be empty).

    Returns ``None`` when the text is not a run command.
    """
    raw = (text or "").strip()
    match = _RUN_RE.match(raw)
    if match is None:
        return None
    query = (match.group(1) or "").strip()
    return query


def is_run_command_prefix(text: str) -> bool:
    """True for ``/r``, ``/ru``, ``/run``, or ``/run …``."""
    raw = (text or "").strip()
    if not raw:
        return False
    if _RUN_PREFIX_RE.match(raw):
        return True
    return parse_run_command(raw) is not None


def format_mission_candidate(mission: Mission) -> str:
    name = (mission.name or "").strip()
    if name and name != mission.id:
        return f"{mission.id} — {name}"
    return mission.id


def format_mission_candidates(missions: list[Mission]) -> list[str]:
    return [format_mission_candidate(m) for m in missions]


def resolve_mission(
    query: str,
    missions: list[Mission],
) -> tuple[Mission | None, list[Mission]]:
    """Resolve a mission by id or name (exact, then unique prefix / substring).

    Returns ``(match, candidates)``:
    - unique match → ``(mission, [])``
    - ambiguous / missing → ``(None, candidate_list)``
    """
    q = (query or "").strip()
    if not q:
        return None, list(missions)

    lowered = q.casefold()
    exact_id = [m for m in missions if m.id.casefold() == lowered]
    if len(exact_id) == 1:
        return exact_id[0], []
    if len(exact_id) > 1:
        return None, exact_id

    exact_name = [m for m in missions if m.name.casefold() == lowered]
    if len(exact_name) == 1:
        return exact_name[0], []
    if len(exact_name) > 1:
        return None, exact_name

    prefixed: list[Mission] = []
    seen: set[str] = set()
    for m in missions:
        if m.id in seen:
            continue
        if m.id.casefold().startswith(lowered) or m.name.casefold().startswith(lowered):
            prefixed.append(m)
            seen.add(m.id)
    if len(prefixed) == 1:
        return prefixed[0], []
    if len(prefixed) > 1:
        return None, prefixed

    contained: list[Mission] = []
    seen.clear()
    for m in missions:
        if m.id in seen:
            continue
        if lowered in m.id.casefold() or lowered in m.name.casefold():
            contained.append(m)
            seen.add(m.id)
    if len(contained) == 1:
        return contained[0], []
    return None, contained


def common_mission_id_prefix(missions: list[Mission]) -> str:
    if not missions:
        return ""
    return os.path.commonprefix([m.id for m in missions])
