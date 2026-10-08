from __future__ import annotations

from install import (
    VERGE_LEGACY_SHORTCUT_NAME,
    VERGE_SHORTCUT_NAME,
    parse_tray_pids,
    remove_verge_shortcuts,
    schtasks_create_args,
    tray_launch_command,
    write_verge_shortcut,
)


def test_tray_task_runs_silent_at_highest_privileges():
    args = schtasks_create_args()
    assert args[0] == "schtasks"
    assert "/RL" in args and args[args.index("/RL") + 1] == "HIGHEST"
    assert "/SC" in args and args[args.index("/SC") + 1] == "ONLOGON"
    cmd = tray_launch_command()
    assert "tray.py" in cmd
    assert "--silent" in cmd
    assert cmd == args[args.index("/TR") + 1]


def _shortcut_target(path) -> str:
    import os
    import subprocess

    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        "$shortcut = $shell.CreateShortcut($env:VERGE_LNK); "
        "Write-Output $shortcut.TargetPath"
    )
    env = os.environ.copy()
    env["VERGE_LNK"] = str(path)
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    return (r.stdout or "").strip()


def test_verge_shortcut_targets_exe_and_replaces_legacy_name(tmp_path):
    exe = tmp_path / "Clash Verge" / "clash-verge.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    startup = tmp_path / "Startup"
    legacy = startup / VERGE_LEGACY_SHORTCUT_NAME
    startup.mkdir()
    legacy.write_bytes(b"old")

    current = write_verge_shortcut(startup, exe)

    assert current.name == VERGE_SHORTCUT_NAME
    assert current.is_file()
    assert not legacy.exists()
    assert _shortcut_target(current) == str(exe)
    remove_verge_shortcuts(startup)
    assert not current.exists()


def test_parse_tray_pids_skips_self_and_blank_lines():
    assert parse_tray_pids("37252\n\nnot-a-pid\n99\n", self_pid=99) == [37252]
    assert parse_tray_pids("", self_pid=1) == []
