from __future__ import annotations

from datetime import datetime, timezone

from croniter import croniter


def local_now() -> datetime:
    """Timezone-aware current local wall time (crontab convention)."""
    return datetime.now().astimezone()


def to_local(dt: datetime) -> datetime:
    """Convert *dt* to the system local timezone.

    Naive values are treated as UTC (legacy daemon state) then converted.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def format_utc_offset(dt: datetime) -> str:
    """Format *dt*'s offset as ``UTC+8`` / ``UTC+05:30`` (not ``CST``)."""
    offset = dt.utcoffset()
    if offset is None:
        return "UTC"
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    if minutes:
        return f"UTC{sign}{hours:02d}:{minutes:02d}"
    return f"UTC{sign}{hours}"


def format_local_stamp(dt: datetime) -> str:
    """``YYYY-MM-DD HH:MM UTC+8`` in local wall time."""
    local = to_local(dt)
    return f"{local.strftime('%Y-%m-%d %H:%M')} {format_utc_offset(local)}"


def next_run(cron_expr: str, from_dt: datetime) -> datetime:
    """Next fire time after *from_dt*, in the same tz as *from_dt* (prefer local)."""
    base = from_dt if from_dt.tzinfo is not None else to_local(from_dt)
    return croniter(cron_expr, base).get_next(datetime)
