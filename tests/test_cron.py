from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from MaintainAll.cron.schedule import next_run
from MaintainAll.daemon.service import MissionLock, is_mission_due


def test_next_run_returns_future_datetime():
    base = datetime(2026, 7, 10, 9, 0, tzinfo=timezone.utc)
    nxt = next_run("0 * * * *", base)
    assert nxt > base
    assert nxt.hour == 10
    assert nxt.minute == 0


def test_is_mission_due_after_interval():
    now = datetime(2026, 7, 10, 11, 0, tzinfo=timezone.utc)
    last_run = datetime(2026, 7, 10, 9, 30, tzinfo=timezone.utc)
    assert is_mission_due("0 * * * *", now, last_run) is True


def test_is_mission_not_due_before_interval():
    now = datetime(2026, 7, 10, 9, 45, tzinfo=timezone.utc)
    last_run = datetime(2026, 7, 10, 9, 30, tzinfo=timezone.utc)
    assert is_mission_due("0 * * * *", now, last_run) is False


def test_is_mission_not_due_until_armed():
    """Fresh schedule must not catch up from epoch (e.g. weekly → fire immediately)."""
    now = datetime(2026, 7, 12, 0, 10, tzinfo=timezone.utc)
    assert is_mission_due("30 9 * * 1", now, None) is False


def test_weekly_due_only_after_armed_tick():
    # Armed Sunday night; Monday 09:30 schedule becomes due Monday morning.
    last_run = datetime(2026, 7, 12, 0, 10, tzinfo=timezone(timedelta(hours=8)))
    before = datetime(2026, 7, 13, 9, 0, tzinfo=timezone(timedelta(hours=8)))
    after = datetime(2026, 7, 13, 9, 30, tzinfo=timezone(timedelta(hours=8)))
    assert is_mission_due("30 9 * * 1", before, last_run) is False
    assert is_mission_due("30 9 * * 1", after, last_run) is True


def test_mission_lock_acquire_release(tmp_path: Path):
    lock_path = tmp_path / "mission-a.lock"
    lock = MissionLock(lock_path)
    assert lock.acquire() is True
    lock.release()
    assert lock.acquire() is True
    lock.release()


def test_mission_lock_blocks_second_holder(tmp_path: Path):
    lock_path = tmp_path / "mission-b.lock"
    first = MissionLock(lock_path)
    second = MissionLock(lock_path)
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()
