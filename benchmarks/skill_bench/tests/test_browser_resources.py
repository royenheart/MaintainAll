"""Measured cgroup resource bounds without destructive allocation or model calls."""

import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
MODULE = SRC / 'skill_bench/browser_resources.py'
DRIVER = SRC / 'skill_bench/browser_driver.py'
from runtime_support import CHROME
USER_BUS = Path('/run/user') / str(__import__('os').getuid()) / 'bus'


def resources(test):
    test.assertTrue(MODULE.is_file(), 'Measured browser resource boundary is absent.')
    return importlib.import_module('skill_bench.browser_resources')


class ResourceBoundaryContracts(unittest.TestCase):
    def test_missing_scope_runtime_fails_closed_without_child_launch(self):
        m = resources(self)
        with patch.object(m, 'SYSTEMD_RUN', Path('/missing-systemd-run')), patch.object(m.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(ValueError, 'resource scope runtime'):
                m.run_scoped(['/usr/bin/true'], 10)
            launch.assert_not_called()

    def test_missing_user_service_bus_has_no_unbounded_fallback(self):
        m = resources(self)
        with patch.object(m, 'runtime_directory', side_effect=ValueError('user manager unavailable')), patch.object(m.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(ValueError, 'user manager'):
                m.run_scoped(['/usr/bin/true'], 10)
            launch.assert_not_called()


@unittest.skipUnless(Path('/usr/bin/systemd-run').is_file() and USER_BUS.is_socket(), 'Optional delegated user systemd manager is unavailable.')
class ActualResourceBoundary(unittest.TestCase):
    def test_harmless_child_inherits_actual_memory_swap_and_pid_limits(self):
        m = resources(self)
        script = 'from pathlib import Path; import json; allocation=bytearray(8*1024*1024); print(json.dumps({"cgroup":Path("/proc/self/cgroup").read_text().strip(),"bytes":len(allocation)}))'
        output = m.run_scoped([sys.executable, '-c', script], 10)
        child = json.loads(output)
        proof = output.resource_boundary
        self.assertTrue(proof['passed'], proof)
        self.assertEqual(proof['limits']['memory.max'], 1073741824)
        self.assertEqual(proof['limits']['memory.swap.max'], 0)
        self.assertEqual(proof['limits']['pids.max'], 128)
        self.assertIn(proof['unit'], child['cgroup'])
        self.assertGreater(proof['observations']['memory.peak'], 8 * 1024 * 1024)
        self.assertEqual(proof['observations']['memory.events']['oom_kill'], 0)

    def test_timeout_removes_entire_exact_scope(self):
        m = resources(self)
        with self.assertRaises(TimeoutError) as failure:
            m.run_scoped([sys.executable, '-c', 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); time.sleep(30)'], 1)
        self.assertTrue(failure.exception.resource_boundary['cleanup_verified'], failure.exception.resource_boundary)

    @unittest.skipUnless(CHROME.is_file() and Path('/usr/bin/bwrap').is_file(), 'Optional Chromium namespace runtime is unavailable.')
    def test_real_chromium_namespace_uses_measured_scope_and_still_captures(self):
        m = importlib.import_module('skill_bench.browser_namespace')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'inputs').mkdir(); (root / 'tools').mkdir()
            shutil.copyfile(DRIVER, root / 'tools/browser_driver.py')
            source = root / 'inputs/source.html'; source.write_text('<!doctype html><div style="width:80px;height:50px;background:#086">Offline</div>')
            tools = {'browser': {'executable': str(CHROME), 'root': str(CHROME.parent), 'driver_sha256': hashlib.sha256(DRIVER.read_bytes()).hexdigest()}}
            original = m.run
            reports = []
            def record(*args, **kwargs):
                output = original(*args, **kwargs); reports.append(output.resource_boundary); return output
            with patch.object(m, 'run', side_effect=record):
                proof = m.namespace_capture(root, source, root / 'evidence', tools, {'samples_ms': [0, 150], 'profiles': ['desktop']}, timeout=20)
            self.assertTrue(proof['passed'], proof)
            self.assertEqual(len(reports), 1)
            self.assertTrue(reports[0]['passed'], reports)
            self.assertGreater(reports[0]['observations']['memory.peak'], 0)
            self.assertEqual(reports[0]['observations']['memory.events']['oom_kill'], 0)


if __name__ == '__main__':
    unittest.main()
