"""Verifier revisions may update trusted code without changing generation inputs."""
import copy
import json
import unittest
from unittest.mock import patch

from skill_bench import visual_runtime as runtime


def identity(name):
    result = {
        'executable': '/opt/' + name + '/binary', 'root': '/opt/' + name,
        'sha256': '1' * 64, 'version': name + ' fixed version', 'size': 100,
        'driver_sha256': '2' * 64,
    }
    if name == 'browser':
        result['namespace_runtime'] = {
            'executable': '/usr/bin/bwrap', 'sha256': '3' * 64,
            'version': 'bubblewrap fixed version', 'method': 'bubblewrap-unshare-all',
            'wrapper_sha256': '4' * 64,
            'network': 'private network namespace without host routes',
            'filesystem': 'readonly frozen inputs and private output',
        }
    return result


class VisualRegradeTests(unittest.TestCase):
    def setUp(self):
        self.frozen = {name: identity(name) for name in ('browser', 'blender')}

    def test_current_drivers_and_wrapper_are_recorded_without_mutating_generation(self):
        generation = {'backend_config': {'visual_tools': self.frozen},
                      'turns': [{'thread_id': 'frozen-thread', 'usage': {'input_tokens': 100},
                                 'artifacts': [{'sha256': '5' * 64, 'snapshot': 'turn-1/artifacts/source.blend'}]}]}
        original_bytes = json.dumps(generation, sort_keys=True).encode()
        current = copy.deepcopy(self.frozen)
        current['browser']['driver_sha256'] = '6' * 64
        current['browser']['namespace_runtime']['wrapper_sha256'] = '7' * 64
        current['blender']['driver_sha256'] = '8' * 64
        with patch.object(runtime, 'discover', return_value=current) as discover:
            actual = runtime.regrade_tools(self.frozen, ['browser_capture', 'native_scene_reopen'])
        self.assertEqual(actual, current)
        self.assertEqual(actual['browser']['driver_sha256'], '6' * 64)
        self.assertEqual(actual['browser']['namespace_runtime']['wrapper_sha256'], '7' * 64)
        self.assertEqual(json.dumps(generation, sort_keys=True).encode(), original_bytes)
        self.assertIsNot(actual, current)
        actual['browser']['namespace_runtime']['wrapper_sha256'] = '9' * 64
        self.assertEqual(current['browser']['namespace_runtime']['wrapper_sha256'], '7' * 64)
        discover.assert_called_once_with({'browser': '/opt/browser/binary', 'blender': '/opt/blender/binary'},
                                         ['browser_capture', 'native_scene_reopen'])

    def test_actual_executable_hash_version_root_and_path_cannot_change(self):
        for name in ('browser', 'blender'):
            required = ['browser_capture'] if name == 'browser' else ['native_scene_reopen']
            for field, changed in (('sha256', 'a' * 64), ('version', 'upgraded'),
                                   ('root', '/opt/another-runtime'), ('executable', '/opt/another-runtime/binary')):
                current = {name: copy.deepcopy(self.frozen[name])}
                current[name][field] = changed
                with self.subTest(name=name, field=field), patch.object(runtime, 'discover', return_value=current):
                    with self.assertRaisesRegex(ValueError, 'executable differs'):
                        runtime.regrade_tools(self.frozen, required)

    def test_namespace_binary_and_method_cannot_change(self):
        for field, changed in (('executable', '/opt/new/bwrap'), ('sha256', 'a' * 64),
                               ('version', 'upgraded bwrap'), ('method', 'host-browser')):
            current = {'browser': copy.deepcopy(self.frozen['browser'])}
            current['browser']['namespace_runtime'][field] = changed
            with self.subTest(field=field), patch.object(runtime, 'discover', return_value=current):
                with self.assertRaisesRegex(ValueError, 'namespace runtime differs'):
                    runtime.regrade_tools(self.frozen, ['playable_motion'])

    def test_required_runtime_missing_from_generation_never_uses_default_installation(self):
        for frozen in ({}, None, {'browser': {'driver_sha256': '1' * 64}}):
            with self.subTest(frozen=frozen), patch.object(runtime, 'discover') as discover:
                with self.assertRaises(ValueError):
                    runtime.regrade_tools(frozen, ['browser_capture'])
                discover.assert_not_called()

    def test_missing_namespace_pin_or_invalid_executable_hash_fail_before_discovery(self):
        for field in ('namespace_runtime', 'sha256', 'version'):
            frozen = copy.deepcopy(self.frozen)
            frozen['browser'].pop(field)
            with self.subTest(field=field), patch.object(runtime, 'discover') as discover:
                with self.assertRaises(ValueError):
                    runtime.regrade_tools(frozen, ['browser_capture'])
                discover.assert_not_called()
        frozen = copy.deepcopy(self.frozen)
        frozen['blender']['sha256'] = 'not a hash'
        with patch.object(runtime, 'discover') as discover:
            with self.assertRaisesRegex(ValueError, 'hash is invalid'):
                runtime.regrade_tools(frozen, ['blender'])
            discover.assert_not_called()

    def test_only_required_tools_are_staged_for_independent_verification(self):
        current = {'blender': copy.deepcopy(self.frozen['blender'])}
        current['blender']['driver_sha256'] = 'a' * 64
        with patch.object(runtime, 'discover', return_value=current) as discover:
            actual = runtime.regrade_tools(self.frozen, ['native_scene_reopen'])
        self.assertEqual(set(actual), {'blender'})
        discover.assert_called_once_with({'blender': '/opt/blender/binary'}, ['native_scene_reopen'])

    def test_non_visual_regrade_needs_no_tools_or_generation_changes(self):
        before = copy.deepcopy(self.frozen)
        with patch.object(runtime, 'discover') as discover:
            self.assertEqual(runtime.regrade_tools(self.frozen, ['svg', 'exact_resume']), {})
            discover.assert_not_called()
        self.assertEqual(self.frozen, before)

    def test_unexpected_tool_population_fails_closed(self):
        for current in ({}, self.frozen):
            with self.subTest(current_keys=list(current)), patch.object(runtime, 'discover', return_value=current):
                with self.assertRaisesRegex(ValueError, 'population changed'):
                    runtime.regrade_tools(self.frozen, ['native_scene_reopen'])


if __name__ == '__main__':
    unittest.main()
