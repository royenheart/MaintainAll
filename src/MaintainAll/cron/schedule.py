from __future__ import annotations

from datetime import datetime

from croniter import croniter


def next_run(cron_expr: str, from_dt: datetime) -> datetime:
    return croniter(cron_expr, from_dt).get_next(datetime)
