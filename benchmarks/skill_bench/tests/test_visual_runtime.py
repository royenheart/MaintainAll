"""Visual capability gates and narrow filesystem grants, with zero model calls."""
import hashlib
import tempfile
import tomllib
from pathlib import Path
import unittest
from unittest.mock import patch

from skill_bench import visual_runtime as runtime
from skill_bench.backends.local_codex import LocalCodexBackend, command, legacy


class VisualRuntimeTests(unittest.TestCase):
    def test_unavailable_explicit_runtime_never_falls_back_to_an_installed_tool(self):
        for name, requirement in [('browser', 'playable_motion'), ('blender', 'native_scene_reopen')]:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'unavailable'):
                runtime.discover({name: '/definitely/missing/visual-runtime'}, [requirement])

    def test_non_visual_cases_receive_no_extra_runtime_or_instruction(self):
        self.assertEqual(runtime.discover({}, ['svg', 'exact_resume']), {})
        self.assertEqual(runtime.environment({}), '')

    def test_tool_grants_preserve_root_deny_and_readonly_inputs_without_auth_access(self):
        tools = {'browser': {'root': '/opt/isolated.browser-runtime', 'executable': '/opt/isolated.browser-runtime/chrome'}}
        with patch.object(legacy().core, 'host_skill_paths', return_value=[]):
            args = command('codex', Path('/runtime/codex'), Path('/workspace'), Path('/renderer'), Path('/private/final'), [], tools=tools)
        configs = [args[i + 1] for i, value in enumerate(args[:-1]) if value == '-c']
        maps = [tomllib.loads(value.split('=', 1)[1].join(['value=', '']))['value'] for value in configs if '.filesystem=' in value]
        fs = maps[-1]
        self.assertEqual(fs[':root'], 'deny')
        self.assertEqual(fs[':workspace_roots'], {'.': 'write', 'skill': 'read', 'inputs': 'read', 'tools': 'read'})
        self.assertEqual(fs['/opt/isolated.browser-runtime'], 'read')
        self.assertNotIn(str(Path.home()), fs)
        self.assertTrue(any('.network.enabled=false' in value for value in configs))

    def test_staged_driver_must_match_runtime_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'driver changed'):
                runtime.stage(Path(tmp), {'browser': {'driver_sha256': '0' * 64}})

    def test_doctor_does_not_claim_unprobed_browser_or_native_capabilities(self):
        with patch.object(legacy().core, 'doctor', return_value={'passed': True}), patch.object(LocalCodexBackend, 'fingerprint', return_value='0' * 64):
            report = LocalCodexBackend().doctor({'renderer': '/renderer'})
        for name in runtime.CAPABILITIES:
            self.assertFalse(report['capabilities'][name])
        self.assertTrue(report['capabilities']['svg'])

    def test_installation_root_cannot_grant_a_whole_home_or_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.git').mkdir()
            binary = root / 'chrome'
            binary.write_text('#!/bin/sh\nexit 0\n')
            binary.chmod(0o700)
            with self.assertRaisesRegex(ValueError, 'dedicated'):
                runtime.discover({'browser': binary}, ['browser_capture'])
