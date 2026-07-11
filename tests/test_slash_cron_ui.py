from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from MaintainAll.config import Settings, normalize_dir
from MaintainAll.cron.describe import describe_cron, is_valid_cron, preview_next_runs
from MaintainAll.daemon.service import (
    list_trusted_missions,
    mission_runtime_key,
)
from MaintainAll.missions.store import update_mission_schedule
from MaintainAll.paths import missions_dir
from MaintainAll.skills.loader import load_skill_body


def _write_mission(root: Path, mission_id: str, schedule: str | None = None) -> None:
    mission_dir = missions_dir(root) / mission_id
    mission_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "id": mission_id,
        "name": mission_id,
        "description": "t",
        "skills": [],
        "schedule": schedule,
        "notify": {"on_complete": False, "on_failure": False},
        "allowed_commands": [],
        "tasks": [
            {
                "id": "main",
                "name": "main",
                "needs": [],
                "instruction": "noop",
                "expect": {"type": "report_section", "name": "summary"},
            }
        ],
    }
    (mission_dir / "MISSION.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )


def test_slash_help_comes_from_decorators():
    # Importing the app registers @slash_command methods.
    from MaintainAll.tui.app import MaintainAllApp  # noqa: F401
    from MaintainAll.tui.slash import format_help_lines, registered_commands

    names = {c.name for c in registered_commands()}
    assert {"help", "run", "solidify", "cron"} <= names
    help_text = "\n".join(format_help_lines())
    assert "/help" in help_text
    assert "/cron" in help_text
    assert "List available slash commands" in help_text
    # Summary must match decorator, not a second hand-written block.
    cron = next(c for c in registered_commands() if c.name == "cron")
    assert cron.summary in help_text


def test_workspace_survives_settings_reload(tmp_path: Path, monkeypatch):
    from MaintainAll.tui.app import MaintainAllApp

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".agents" / "missions").mkdir(parents=True)
    app = MaintainAllApp()
    app.workspace = Path(normalize_dir(tmp_path))
    app.settings = Settings(data_dir=str(tmp_path / "data"), trusted_dirs=[])
    app._sync_settings_repo_path()
    assert Path(app.settings.repo_path) == app.workspace

    # Simulate Settings save → load_settings resets default repo_path in Settings,
    # but workspace must stay cwd-based.
    app.settings = Settings(data_dir=str(tmp_path / "data"))
    app._sync_settings_repo_path()
    assert app._repo() == app.workspace
    assert str(app.workspace) == normalize_dir(tmp_path)


def test_update_mission_schedule(tmp_path: Path):
    _write_mission(tmp_path, "m1", schedule=None)
    path = update_mission_schedule(tmp_path, "m1", "0 * * * *")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["schedule"] == "0 * * * *"
    update_mission_schedule(tmp_path, "m1", None)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["schedule"] is None


def test_list_trusted_missions_two_repos_same_id(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _write_mission(a, "shared", schedule="0 * * * *")
    _write_mission(b, "shared", schedule=None)
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        trusted_dirs=[str(a), str(b)],
    )
    views = list_trusted_missions(settings)
    assert len(views) == 2
    keys = {v.runtime_key for v in views}
    assert mission_runtime_key(a, "shared") in keys
    assert mission_runtime_key(b, "shared") in keys
    by_repo = {normalize_dir(v.repo): v for v in views}
    assert by_repo[normalize_dir(a)].schedule == "0 * * * *"
    assert by_repo[normalize_dir(b)].schedule is None
    assert by_repo[normalize_dir(a)].next_run_at is not None


def test_cron_describe_and_validate():
    assert is_valid_cron("0 * * * *")
    assert not is_valid_cron("not a cron")
    assert not is_valid_cron("")
    desc = describe_cron("0 * * * *")
    assert desc and "Invalid" not in desc
    # Anchor in local tz so "midnight" means local midnight.
    from MaintainAll.cron.schedule import local_now

    local = local_now().replace(hour=12, minute=0, second=0, microsecond=0)
    runs = preview_next_runs("0 0 * * *", count=2, from_dt=local)
    assert len(runs) == 2
    assert runs[0] < runs[1]
    assert runs[0].hour == 0
    assert runs[0].tzinfo is not None


def test_cron_field_index_and_help():
    from MaintainAll.cron.describe import cron_field_index, format_cron_part_help, format_cron_parts_bar

    expr = "0 * 1 2 3"
    # cursor in first token
    assert cron_field_index(expr, 0) == 0
    assert cron_field_index(expr, 1) == 0
    # after first space → hour
    assert cron_field_index(expr, 2) == 1
    assert cron_field_index("@hourly", 1) == -1
    help_min = format_cron_part_help(0)
    assert "0-59" in help_min
    assert "*" in help_min and "any value" in help_min
    assert "@yearly" in help_min
    help_wd = format_cron_part_help(4)
    assert "SUN-SAT" in help_wd
    assert "weekday" in format_cron_parts_bar(4)
    assert "minute" in format_cron_parts_bar(0)


def test_skill_body_loaded_for_markdown(tmp_path: Path):
    skill = tmp_path / "demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\n\n# Hello\n\nBody here.\n",
        encoding="utf-8",
    )
    body = load_skill_body(skill)
    assert "# Hello" in body
    assert "Body here" in body
    assert "name: demo" not in body


def test_detail_modal_skill_uses_markdown():
    from MaintainAll.tui.modals import DetailModal

    src = Path(DetailModal._compose_body.__code__.co_filename).read_text(encoding="utf-8")
    # Ensure skill path yields Markdown widget (source-level check).
    assert "Markdown" in src
    assert "load_skill_body" in src
