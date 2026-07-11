from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import tomllib

from MaintainAll.config import (
    Settings,
    add_trusted_dir,
    effective_trusted_dirs,
    is_trusted_dir,
    load_settings,
    normalize_dir,
    normalize_trusted_dirs,
    save_non_secrets,
)
from MaintainAll.daemon.service import (
    load_daemon_state,
    migrate_legacy_daemon_state,
    mission_runtime_key,
    save_daemon_state,
    scan_once,
)
from MaintainAll.paths import agents_dir, daemon_state_path, missions_dir


def _write_scheduled_mission(root: Path, mission_id: str = "shared-check") -> None:
    mission_dir = missions_dir(root) / mission_id
    mission_dir.mkdir(parents=True, exist_ok=True)
    (mission_dir / "MISSION.yaml").write_text(
        "\n".join(
            [
                f"id: {mission_id}",
                f"name: {mission_id}",
                "description: test",
                "skills: []",
                "schedule: '0 * * * *'",
                "notify:",
                "  on_complete: false",
                "  on_failure: false",
                "allowed_commands: []",
                "tasks:",
                "  - id: main",
                "    name: main",
                "    needs: []",
                "    instruction: noop",
                "    expect:",
                "      type: report_section",
                "      name: summary",
            ]
        ),
        encoding="utf-8",
    )


def test_normalize_trusted_dirs_dedupes(tmp_path: Path):
    a = tmp_path / "a"
    a.mkdir()
    paths = normalize_trusted_dirs([str(a), str(a), f"{a}/."])
    assert paths == [normalize_dir(a)]


def test_trusted_dirs_migrate_from_repo_path(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAINTAINALL_CONFIG_DIR", str(tmp_path))
    repo = tmp_path / "ws"
    repo.mkdir()
    (tmp_path / "config.toml").write_text(
        f'repo_path = "{repo}"\nmodel = "deepseek-v4-flash"\n',
        encoding="utf-8",
    )
    loaded = load_settings(config_dir_path=tmp_path)
    assert loaded.trusted_dirs == [normalize_dir(repo)]
    assert effective_trusted_dirs(loaded) == [normalize_dir(repo)]


def test_trusted_dirs_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MAINTAINALL_CONFIG_DIR", str(tmp_path))
    a = tmp_path / "one"
    b = tmp_path / "two"
    a.mkdir()
    b.mkdir()
    s = Settings(
        repo_path=str(a),
        data_dir=str(tmp_path / "data"),
        trusted_dirs=[str(a), str(b)],
    )
    save_non_secrets(s, config_dir=tmp_path)
    raw = tomllib.loads((tmp_path / "config.toml").read_text())
    assert normalize_dir(a) in raw["trusted_dirs"]
    assert normalize_dir(b) in raw["trusted_dirs"]
    loaded = load_settings(config_dir_path=tmp_path)
    assert set(loaded.trusted_dirs) == {normalize_dir(a), normalize_dir(b)}


def test_add_trusted_dir_and_is_trusted(tmp_path: Path):
    ws = tmp_path / "proj"
    other = tmp_path / "other"
    ws.mkdir()
    other.mkdir()
    # Explicit list empty → not trusted; daemon scans nothing until Trust/Settings.
    s = Settings(repo_path=str(ws), trusted_dirs=[])
    assert not is_trusted_dir(s, ws)
    assert effective_trusted_dirs(s) == []
    assert not is_trusted_dir(s, other)
    s2 = add_trusted_dir(Settings(repo_path=str(other), trusted_dirs=[]), ws)
    assert normalize_dir(ws) in s2.trusted_dirs
    assert is_trusted_dir(s2, ws)


def test_mission_runtime_key_disambiguates(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert mission_runtime_key(a, "x") != mission_runtime_key(b, "x")
    assert mission_runtime_key(a, "x").endswith("::x")


def test_migrate_legacy_daemon_state(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    legacy = agents_dir(repo) / ".daemon_state.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text('{"old-m": "2026-01-01T00:00:00+00:00"}', encoding="utf-8")
    merged = migrate_legacy_daemon_state({}, [repo])
    key = mission_runtime_key(repo, "old-m")
    assert merged[key] == "2026-01-01T00:00:00+00:00"


def test_scan_once_two_repos_same_mission_id(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()
    _write_scheduled_mission(repo_a, "shared-check")
    _write_scheduled_mission(repo_b, "shared-check")

    # Pre-arm so scan executes (unarmed schedules only arm, never catch up).
    save_daemon_state(
        {
            mission_runtime_key(repo_a, "shared-check"): "2026-01-01T00:00:00+00:00",
            mission_runtime_key(repo_b, "shared-check"): "2026-01-01T00:00:00+00:00",
        },
        data_dir=data,
    )

    settings = Settings(
        repo_path=str(repo_a),
        data_dir=str(data),
        trusted_dirs=[str(repo_a), str(repo_b)],
    )
    calls: list[tuple[str, str]] = []

    def fake_run(mission, *, settings, skip_review=True, llm=None):
        calls.append((settings.repo_path, mission.id))
        return {
            "validation_ok": True,
            "repo_path": settings.repo_path,
            "mission_draft": {"id": mission.id},
        }

    with (
        patch("MaintainAll.daemon.service.is_mission_due", return_value=True),
        patch("MaintainAll.daemon.service.run_mission", side_effect=fake_run),
        patch("MaintainAll.daemon.service.write_report", return_value=Path("x.md")),
        patch("MaintainAll.daemon.service._maybe_notify"),
    ):
        scan_once(settings)

    assert len(calls) == 2
    repos = {normalize_dir(p) for p, _mid in calls}
    assert repos == {normalize_dir(repo_a), normalize_dir(repo_b)}
    state = load_daemon_state(data_dir=data)
    assert mission_runtime_key(repo_a, "shared-check") in state
    assert mission_runtime_key(repo_b, "shared-check") in state
    assert daemon_state_path(data_dir=data).exists()


def test_scan_once_arms_unseen_schedule_without_running(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_scheduled_mission(repo, "weekly")
    settings = Settings(
        repo_path=str(repo),
        data_dir=str(data),
        trusted_dirs=[str(repo)],
    )
    with patch("MaintainAll.daemon.service.run_mission") as run_m:
        scan_once(settings)
        run_m.assert_not_called()
    state = load_daemon_state(data_dir=data)
    assert mission_runtime_key(repo, "weekly") in state


def test_trust_dir_modal_exists():
    from MaintainAll.tui.modals import TrustDirModal

    modal = TrustDirModal("/tmp/example")
    assert modal.path == "/tmp/example"
