"""Patch PROCESS-NAME rules in a Clash/mihomo YAML mapping."""

from __future__ import annotations

PROCESS_PREFIXES = (
    "PROCESS-NAME,",
    "PROCESS-PATH,",
    "PROCESS-NAME-REGEX,",
    "PROCESS-PATH-REGEX,",
    "PROCESS-NAME-WILDCARD,",
    "PROCESS-PATH-WILDCARD,",
)


def _rule_str(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    return str(item).strip()


def is_process_rule(item: object) -> bool:
    s = _rule_str(item)
    if s.startswith("#") and "未选择进程" in s:
        return True
    u = s.upper()
    return any(u.startswith(p.upper()) for p in PROCESS_PREFIXES)


def is_match_rule(item: object) -> bool:
    return _rule_str(item).upper().startswith("MATCH,")


def normalize_exe(name: str) -> str:
    n = name.strip().strip('"')
    if not n:
        return ""
    if "\\" in n or "/" in n:
        n = n.replace("/", "\\").rsplit("\\", 1)[-1]
    if not n.lower().endswith(".exe"):
        n += ".exe"
    return n


def unique_exes(names: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        n = normalize_exe(raw)
        if not n:
            continue
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def replace_process_rules(data: dict, processes: list[str]) -> dict:
    """Keep LAN/other rules; put PROCESS-NAME lines before MATCH."""
    rules = list(data.get("rules") or [])
    match_rule = None
    kept: list = []
    for item in rules:
        if is_process_rule(item):
            continue
        if is_match_rule(item):
            match_rule = item
            continue
        kept.append(item)
    for exe in unique_exes(processes):
        kept.append(f"PROCESS-NAME,{exe},proxy")
    kept.append(match_rule if match_rule is not None else "MATCH,DIRECT")
    data["rules"] = kept
    return data


def process_names_from_rules(data: dict) -> list[str]:
    out: list[str] = []
    for item in data.get("rules") or []:
        s = _rule_str(item)
        if s.upper().startswith("PROCESS-NAME,") and not s.upper().startswith("PROCESS-NAME-"):
            parts = s.split(",")
            if len(parts) >= 2:
                out.append(normalize_exe(parts[1]))
    return unique_exes(out)
