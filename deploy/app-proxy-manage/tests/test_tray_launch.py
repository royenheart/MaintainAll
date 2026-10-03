from __future__ import annotations

from install import parse_tray_pids, schtasks_create_args, tray_launch_command


def test_tray_task_runs_silent_at_highest_privileges():
    args = schtasks_create_args()
    assert args[0] == "schtasks"
    assert "/RL" in args and args[args.index("/RL") + 1] == "HIGHEST"
    assert "/SC" in args and args[args.index("/SC") + 1] == "ONLOGON"
    cmd = tray_launch_command()
    assert "tray.py" in cmd
    assert "--silent" in cmd
    assert cmd == args[args.index("/TR") + 1]


def test_parse_tray_pids_skips_self_and_blank_lines():
    assert parse_tray_pids("37252\n\nnot-a-pid\n99\n", self_pid=99) == [37252]
    assert parse_tray_pids("", self_pid=1) == []
