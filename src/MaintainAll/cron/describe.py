from __future__ import annotations

from datetime import datetime

from croniter import croniter

# crontab.guru-style common presets (expression, short label)
CRON_PRESETS: list[tuple[str, str]] = [
    ("* * * * *", "Every minute"),
    ("0 * * * *", "Hourly"),
    ("0 0 * * *", "Daily midnight"),
    ("0 0 * * 0", "Weekly Sunday"),
    ("0 0 1 * *", "Monthly 1st"),
]

# Five standard fields — labels match crontab.guru
CRON_FIELD_NAMES: tuple[str, ...] = (
    "minute",
    "hour",
    "day",
    "month",
    "weekday",
)

# Operators always shown (crontab.guru left column)
CRON_OPERATORS: tuple[tuple[str, str], ...] = (
    ("*", "any value"),
    (",", "value list separator"),
    ("-", "range of values"),
    ("/", "step values"),
)

# Non-standard @aliases (crontab.guru)
CRON_ALIASES: tuple[tuple[str, str], ...] = (
    ("@yearly", "(non-standard)"),
    ("@annually", "(non-standard)"),
    ("@monthly", "(non-standard)"),
    ("@weekly", "(non-standard)"),
    ("@daily", "(non-standard)"),
    ("@hourly", "(non-standard)"),
    ("@reboot", "(non-standard)"),
)

# Per-field allowed values / alternatives (shown for the active field)
CRON_FIELD_HINTS: tuple[tuple[tuple[str, str], ...], ...] = (
    (("0-59", "allowed values"),),
    (("0-23", "allowed values"),),
    (("1-31", "allowed values"),),
    (
        ("1-12", "allowed values"),
        ("JAN-DEC", "alternative single values"),
    ),
    (
        ("0-6", "allowed values"),
        ("SUN-SAT", "alternative single values"),
        ("7", "sunday (non-standard)"),
    ),
)


def is_valid_cron(expr: str) -> bool:
    text = (expr or "").strip()
    if not text:
        return False
    try:
        if hasattr(croniter, "is_valid"):
            return bool(croniter.is_valid(text))
        croniter(text)
        return True
    except (ValueError, KeyError, TypeError):
        return False


def describe_cron(expr: str) -> str:
    """Human-readable description (cron-descriptor / crontab.guru style)."""
    text = (expr or "").strip()
    if not text:
        return "(no schedule)"
    if not is_valid_cron(text):
        return "Invalid cron expression"
    try:
        from cron_descriptor import Options, get_description

        opts = Options()
        opts.locale_code = "zh_CN"
        try:
            return get_description(text, opts)
        except Exception:
            return get_description(text)
    except Exception as exc:
        return f"(describe failed: {exc})"


def preview_next_runs(
    expr: str, *, count: int = 5, from_dt: datetime | None = None
) -> list[datetime]:
    """Next fire times in **local** timezone (same convention as system crontab)."""
    from MaintainAll.cron.schedule import local_now, to_local

    text = (expr or "").strip()
    if not is_valid_cron(text):
        return []
    base = to_local(from_dt) if from_dt is not None else local_now()
    out: list[datetime] = []
    cursor = base
    for _ in range(count):
        nxt = croniter(text, cursor).get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=base.tzinfo)
        else:
            nxt = nxt.astimezone(base.tzinfo)
        out.append(nxt)
        cursor = nxt
    return out


def cron_field_index(expr: str, cursor: int) -> int:
    """Return 0–4 for which of the five cron fields the cursor is in.

    For ``@hourly``-style aliases (single token starting with ``@``), returns ``-1``.
    """
    text = expr if expr is not None else ""
    pos = max(0, min(int(cursor), len(text)))
    stripped = text.lstrip()
    if stripped.startswith("@") and len(stripped.split()) == 1:
        return -1

    field = 0
    i = 0
    n = len(text)
    while i < n and text[i].isspace():
        if i >= pos:
            return 0
        i += 1
    while i < n and field < 5:
        start = i
        while i < n and not text[i].isspace():
            i += 1
        end = i
        if start <= pos <= end:
            return field
        ws_start = i
        while i < n and text[i].isspace():
            i += 1
        if ws_start <= pos < i:
            return min(field + 1, 4)
        field += 1
    return min(field, 4)


def format_cron_part_help(field_index: int) -> str:
    """Plain-text help block for the active cron field (crontab.guru table)."""
    lines: list[str] = []
    lines.append("Operators:")
    for token, meaning in CRON_OPERATORS:
        lines.append(f"  {token:<8} {meaning}")
    lines.append("")
    lines.append("Aliases (non-standard):")
    for token, meaning in CRON_ALIASES:
        lines.append(f"  {token:<10} {meaning}")
    if 0 <= field_index < len(CRON_FIELD_NAMES):
        name = CRON_FIELD_NAMES[field_index]
        lines.append("")
        lines.append(f"Field «{name}» allowed values:")
        for token, meaning in CRON_FIELD_HINTS[field_index]:
            lines.append(f"  {token:<10} {meaning}")
    elif field_index < 0:
        lines.append("")
        lines.append("Alias mode — enter e.g. @hourly instead of five fields.")
    return "\n".join(lines)


def format_cron_parts_bar(active: int) -> str:
    """Rich markup bar: minute hour day month weekday with active bold/cyan."""
    parts: list[str] = []
    for i, name in enumerate(CRON_FIELD_NAMES):
        if i == active:
            parts.append(f"[bold cyan]{name}[/]")
        else:
            parts.append(f"[dim]{name}[/]")
    return "  ".join(parts)
