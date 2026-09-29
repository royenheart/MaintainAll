import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import supervisor_refresh as refresh


class ReadSupervisorPidTest(unittest.TestCase):
    def test_reads_pid_from_paseo_pid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "paseo.pid").write_text(
                json.dumps({"pid": 2228262, "listen": "127.0.0.1:6767"}),
                encoding="utf-8",
            )
            self.assertEqual(refresh.read_supervisor_pid(home), 2228262)

    def test_missing_or_invalid_pid_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertIsNone(refresh.read_supervisor_pid(home))
            (home / "paseo.pid").write_text("not json", encoding="utf-8")
            self.assertIsNone(refresh.read_supervisor_pid(home))
            (home / "paseo.pid").write_text('{"pid": "nope"}', encoding="utf-8")
            self.assertIsNone(refresh.read_supervisor_pid(home))


class InstalledPackageMtimeTest(unittest.TestCase):
    def test_newest_manifest_wins_and_missing_dirs_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scope = Path(tmp)
            (scope / "cli").mkdir()
            cli_manifest = scope / "cli" / "package.json"
            cli_manifest.write_text("{}", encoding="utf-8")
            old = 1_000.0
            new = 2_000.0
            cli_manifest.touch()
            import os

            os.utime(cli_manifest, (old, old))
            self.assertEqual(refresh.installed_package_mtime(scope), old)
            (scope / "server").mkdir()
            server_manifest = scope / "server" / "package.json"
            server_manifest.write_text("{}", encoding="utf-8")
            os.utime(server_manifest, (new, new))
            self.assertEqual(refresh.installed_package_mtime(scope), new)

    def test_empty_scope_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(refresh.installed_package_mtime(Path(tmp)))


class BusyAgentIdsTest(unittest.TestCase):
    def test_only_running_and_initializing_count_as_busy(self) -> None:
        agents = [
            {"id": "a1", "status": "running"},
            {"id": "a2", "status": "initializing"},
            {"id": "a3", "status": "idle"},
            {"id": "a4", "status": "closed"},
            {"id": "a5", "status": "error"},
            {"shortId": "a6", "status": "running"},
        ]
        self.assertEqual(refresh.busy_agent_ids(agents), ["a1", "a2", "a6"])

    def test_non_list_payload_yields_nobody(self) -> None:
        self.assertEqual(refresh.busy_agent_ids({"status": "running"}), [])


class DecideTest(unittest.TestCase):
    def base_kwargs(self):
        return dict(
            service_active=True,
            supervisor_pid=100,
            supervisor_start=1_000.0,
            package_mtime=2_000.0,
            busy_ids=[],
        )

    def test_inactive_service_is_a_noop(self) -> None:
        action, _ = refresh.decide(**{**self.base_kwargs(), "service_active": False})
        self.assertEqual(action, refresh.ACTION_NOOP)

    def test_no_supervisor_pid_is_a_noop(self) -> None:
        action, _ = refresh.decide(**{**self.base_kwargs(), "supervisor_pid": None})
        self.assertEqual(action, refresh.ACTION_NOOP)

    def test_package_older_than_supervisor_is_a_noop(self) -> None:
        action, _ = refresh.decide(**{**self.base_kwargs(), "package_mtime": 500.0})
        self.assertEqual(action, refresh.ACTION_NOOP)

    def test_unknown_agent_state_skips_restart(self) -> None:
        action, reason = refresh.decide(**{**self.base_kwargs(), "busy_ids": None})
        self.assertEqual(action, refresh.ACTION_SKIP)
        self.assertIn("not safe", reason)

    def test_busy_agents_skip_restart(self) -> None:
        action, reason = refresh.decide(**{**self.base_kwargs(), "busy_ids": ["a1"]})
        self.assertEqual(action, refresh.ACTION_SKIP)
        self.assertIn("a1", reason)

    def test_stale_package_and_idle_agents_restart(self) -> None:
        action, _ = refresh.decide(**self.base_kwargs())
        self.assertEqual(action, refresh.ACTION_RESTART)


class CollectBusyIdsTest(unittest.TestCase):
    def fake_runner(self, payload: str, returncode: int = 0):
        def runner(cmd, timeout):
            import subprocess

            return subprocess.CompletedProcess(cmd, returncode, payload, "")

        return runner

    def test_parses_ls_json(self) -> None:
        payload = json.dumps([{"id": "a1", "status": "running"}, {"id": "a2", "status": "idle"}])
        self.assertEqual(refresh.collect_busy_ids("paseo", runner=self.fake_runner(payload)), ["a1"])

    def test_nonzero_exit_or_bad_json_returns_none(self) -> None:
        self.assertIsNone(
            refresh.collect_busy_ids("paseo", runner=self.fake_runner("[]", returncode=1))
        )
        self.assertIsNone(refresh.collect_busy_ids("paseo", runner=self.fake_runner("nope")))

    def test_runner_exception_returns_none(self) -> None:
        def runner(cmd, timeout):
            raise OSError("paseo missing")

        self.assertIsNone(refresh.collect_busy_ids("paseo", runner=runner))


class MainTest(unittest.TestCase):
    def make_stale_scope(self, home: Path) -> Path:
        scope = home / "scope"
        (scope / "cli").mkdir(parents=True)
        manifest = scope / "cli" / "package.json"
        manifest.write_text("{}", encoding="utf-8")
        import os

        os.utime(manifest, (2_000.0, 2_000.0))
        return scope

    def base_patches(self):
        return [
            mock.patch.object(refresh, "systemctl_is_active", return_value=True),
            mock.patch.object(refresh, "read_supervisor_pid", return_value=100),
            mock.patch.object(refresh, "pid_alive", return_value=True),
            mock.patch.object(refresh, "process_start_epoch", return_value=1_000.0),
            mock.patch.object(refresh, "collect_busy_ids", return_value=[]),
        ]

    def main_args(self, home: Path, scope: Path, extra: list[str]) -> list[str]:
        return [
            "--home",
            str(home),
            "--watch-dir",
            str(scope),
            "--paseo-bin",
            "paseo",
            "--settle-seconds",
            "0",
            *extra,
        ]

    def enter(self, stack, patcher):
        return stack.enter_context(patcher)

    def test_dry_run_never_restarts(self) -> None:
        import contextlib

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            home = Path(tmp)
            for patcher in self.base_patches():
                stack.enter_context(patcher)
            stack.enter_context(mock.patch.object(refresh, "wait_for_quiescence", return_value=True))
            run_mock = stack.enter_context(mock.patch.object(refresh, "run"))
            scope = self.make_stale_scope(home)
            rc = refresh.main(self.main_args(home, scope, ["--dry-run"]))
            self.assertEqual(rc, 0)
            run_mock.assert_not_called()

    def test_restart_calls_systemctl(self) -> None:
        import contextlib
        import subprocess

        restarted: list[list[str]] = []

        def runner(cmd, timeout):
            restarted.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            home = Path(tmp)
            for patcher in self.base_patches():
                stack.enter_context(patcher)
            stack.enter_context(mock.patch.object(refresh, "wait_for_quiescence", return_value=True))
            stack.enter_context(mock.patch.object(refresh, "run", side_effect=runner))
            scope = self.make_stale_scope(home)
            rc = refresh.main(self.main_args(home, scope, []))
            self.assertEqual(rc, 0)
            self.assertEqual(restarted, [["systemctl", "--user", "restart", "paseo.service"]])

    def test_skip_when_self_update_is_running(self) -> None:
        import contextlib

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            home = Path(tmp)
            for patcher in self.base_patches():
                stack.enter_context(patcher)
            stack.enter_context(mock.patch.object(refresh, "wait_for_quiescence", return_value=False))
            busy_mock = stack.enter_context(mock.patch.object(refresh, "collect_busy_ids"))
            run_mock = stack.enter_context(mock.patch.object(refresh, "run"))
            scope = self.make_stale_scope(home)
            rc = refresh.main(self.main_args(home, scope, []))
            self.assertEqual(rc, 0)
            busy_mock.assert_not_called()
            run_mock.assert_not_called()

    def test_noop_when_package_not_newer(self) -> None:
        import contextlib

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            home = Path(tmp)
            for patcher in self.base_patches():
                stack.enter_context(patcher)
            stack.enter_context(mock.patch.object(refresh, "process_start_epoch", return_value=3_000.0))
            wait_mock = stack.enter_context(mock.patch.object(refresh, "wait_for_quiescence"))
            run_mock = stack.enter_context(mock.patch.object(refresh, "run"))
            scope = self.make_stale_scope(home)
            rc = refresh.main(self.main_args(home, scope, []))
            self.assertEqual(rc, 0)
            wait_mock.assert_not_called()
            run_mock.assert_not_called()


class SelfUpdateDetectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cgroup_root = self.root / "cgroup"
        self.proc_root = self.root / "proc"
        self.cg = "user.slice/user-1000.slice/user@1000.service/app.slice/paseo.service"
        cg_dir = self.cgroup_root / self.cg
        cg_dir.mkdir(parents=True)
        (cg_dir / "cgroup.procs").write_text("101\n102\n", encoding="ascii")
        nested = cg_dir / "child"
        nested.mkdir()
        (nested / "cgroup.procs").write_text("103\n", encoding="ascii")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_cmdline(self, pid: int, *argv: str) -> None:
        proc_dir = self.proc_root / str(pid)
        proc_dir.mkdir(parents=True, exist_ok=True)
        (proc_dir / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")

    def test_cgroup_pids_collects_nested_procs(self) -> None:
        self.assertEqual(refresh.cgroup_pids(self.cg, self.cgroup_root), [101, 102, 103])

    def test_cgroup_pids_unknown_group_is_empty(self) -> None:
        self.assertEqual(refresh.cgroup_pids("missing.slice/x.service", self.cgroup_root), [])

    def test_cmdline_matcher_accepts_npm_binary_and_npm_cli(self) -> None:
        self.write_cmdline(101, "npm", "install", "--global", "@getpaseo/cli@latest")
        self.write_cmdline(102, "/home/u/.nvm/versions/node/v24/bin/node", "/home/u/.nvm/versions/node/v24/lib/node_modules/npm/bin/npm-cli.js", "install", "-g", "x")
        self.write_cmdline(103, "node", "scripts/post-install.js")
        self.assertTrue(refresh.cmdline_is_npm_install(101, self.proc_root))
        self.assertTrue(refresh.cmdline_is_npm_install(102, self.proc_root))
        self.assertFalse(refresh.cmdline_is_npm_install(103, self.proc_root))
        self.assertFalse(refresh.cmdline_is_npm_install(999, self.proc_root))

    def test_npm_busy_requires_install_in_cgroup(self) -> None:
        self.write_cmdline(101, "npm", "install", "--global", "@getpaseo/cli@latest")
        self.write_cmdline(102, "paseo", "daemon", "run")
        self.assertTrue(refresh.npm_busy(self.cg, self.cgroup_root, self.proc_root))
        # An npm install outside the service cgroup (user's own terminal)
        # must not block the refresh.
        self.assertFalse(
            refresh.npm_busy("other.scope", self.cgroup_root, self.proc_root)
        )


class WaitForQuiescenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cgroup_root = self.root / "cgroup"
        self.proc_root = self.root / "proc"
        self.cg = "paseo.service"
        cg_dir = self.cgroup_root / self.cg
        cg_dir.mkdir(parents=True)
        (cg_dir / "cgroup.procs").write_text("101\n", encoding="ascii")
        proc_dir = self.proc_root / "101"
        proc_dir.mkdir(parents=True)
        (proc_dir / "cmdline").write_bytes(b"npm\0install\0-g\0x\0")
        # Worker 201 started long ago.
        worker_dir = self.proc_root / "201"
        worker_dir.mkdir(parents=True)
        (worker_dir / "cmdline").write_bytes(b"node\0paseo\0")
        import os

        os.utime(worker_dir, (1_000.0, 1_000.0))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def runner(self, cmd, timeout, status_payload='{"workerPid": 201}'):
        import subprocess

        if "ControlGroup" in cmd:
            return subprocess.CompletedProcess(cmd, 0, self.cg + "\n", "")
        return subprocess.CompletedProcess(cmd, 0, status_payload, "")

    def fake_clock(self, start: float = 0.0):
        ticks = iter([start, start + 1, start + 2, start + 3, start + 1000])
        return lambda: next(ticks)

    def test_not_quiescent_while_npm_in_cgroup(self) -> None:
        self.assertFalse(
            refresh.daemon_quiescent(
                "paseo.service",
                "paseo",
                runner=self.runner,
                cgroup_root=self.cgroup_root,
                proc_root=self.proc_root,
                now=lambda: 2_000.0,
            )
        )

    def test_quiescent_when_npm_gone_and_worker_old(self) -> None:
        (self.proc_root / "101" / "cmdline").write_bytes(b"node\0daemon\0")
        self.assertTrue(
            refresh.daemon_quiescent(
                "paseo.service",
                "paseo",
                runner=self.runner,
                cgroup_root=self.cgroup_root,
                proc_root=self.proc_root,
                now=lambda: 2_000.0,
            )
        )

    def test_not_quiescent_while_worker_young(self) -> None:
        import os

        (self.proc_root / "101" / "cmdline").write_bytes(b"node\0daemon\0")
        os.utime(self.proc_root / "201", (1_990.0, 1_990.0))  # 10s ago
        self.assertFalse(
            refresh.daemon_quiescent(
                "paseo.service",
                "paseo",
                runner=self.runner,
                cgroup_root=self.cgroup_root,
                proc_root=self.proc_root,
                now=lambda: 2_000.0,
            )
        )

    def test_not_quiescent_while_status_unreachable(self) -> None:
        import subprocess

        (self.proc_root / "101" / "cmdline").write_bytes(b"node\0daemon\0")

        def runner(cmd, timeout):
            if "ControlGroup" in cmd:
                return subprocess.CompletedProcess(cmd, 0, self.cg + "\n", "")
            return subprocess.CompletedProcess(cmd, 1, "", "boom")

        self.assertFalse(
            refresh.daemon_quiescent(
                "paseo.service",
                "paseo",
                runner=runner,
                cgroup_root=self.cgroup_root,
                proc_root=self.proc_root,
                now=lambda: 2_000.0,
            )
        )

    def test_daemon_without_worker_pid_field_is_settled(self) -> None:
        (self.proc_root / "101" / "cmdline").write_bytes(b"node\0daemon\0")
        self.assertTrue(
            refresh.daemon_quiescent(
                "paseo.service",
                "paseo",
                runner=lambda cmd, timeout: self.runner(cmd, timeout, status_payload="{}"),
                cgroup_root=self.cgroup_root,
                proc_root=self.proc_root,
                now=lambda: 2_000.0,
            )
        )

    def test_waits_until_quiescent(self) -> None:
        (self.proc_root / "101" / "cmdline").write_bytes(b"node\0daemon\0")
        slept: list[float] = []
        done = refresh.wait_for_quiescence(
            "paseo.service",
            "paseo",
            runner=self.runner,
            cgroup_root=self.cgroup_root,
            proc_root=self.proc_root,
            sleep=slept.append,
            monotonic=self.fake_clock(),
            now=lambda: 2_000.0,
        )
        self.assertTrue(done)
        self.assertEqual(slept, [])

    def test_times_out_while_never_quiescent(self) -> None:
        logs: list[str] = []
        done = refresh.wait_for_quiescence(
            "paseo.service",
            "paseo",
            runner=self.runner,
            cgroup_root=self.cgroup_root,
            proc_root=self.proc_root,
            sleep=lambda _s: None,
            monotonic=self.fake_clock(),
            now=lambda: 2_000.0,
            timeout=10.0,
            poll=5.0,
            log=logs.append,
        )
        self.assertFalse(done)
        self.assertTrue(logs)


if __name__ == "__main__":
    unittest.main()
