"""Capability promotion requires real namespace action/audio positives and negatives."""

import hashlib
import importlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
MODULE = SRC / 'skill_bench/action_acceptance.py'
DRIVER = SRC / 'skill_bench/browser_driver.py'
from runtime_support import CHROME


def acceptance(test):
    test.assertTrue(MODULE.is_file(), 'Independent action/audio acceptance implementation is absent.')
    return importlib.import_module('skill_bench.action_acceptance')


def stage(root):
    (root / 'inputs').mkdir(); (root / 'tools').mkdir()
    shutil.copyfile(DRIVER, root / 'tools/browser_driver.py')
    return {'browser': {'executable': str(CHROME), 'root': str(CHROME.parent),
                        'driver_sha256': hashlib.sha256(DRIVER.read_bytes()).hexdigest()}}


class ActionAcceptanceContracts(unittest.TestCase):
    def test_capability_failure_preserves_separate_results_and_never_uses_a_host_fallback(self):
        m = acceptance(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); tools = stage(root)
            with patch.object(m, 'namespace_capture', side_effect=ValueError('Namespace unavailable')) as capture:
                result = m.action_doctor(root, tools)
            self.assertFalse(result['action_trace_capture']['passed'])
            self.assertFalse(result['web_audio_probe']['passed'])
            self.assertEqual(result['generation_calls'], 0)
            self.assertEqual(capture.call_count, 6)
            self.assertTrue(result['action_trace_capture']['failures'])
            self.assertTrue(result['web_audio_probe']['failures'])

    def test_requested_modes_and_claimed_measurement_summary_cannot_promote_audio(self):
        m = acceptance(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); tools = stage(root)
            fake = {'passed': True, 'frames': [], 'dom_samples': [], 'input_events': [], 'audio_samples': [],
                    'audio_probe': {'mode': 'tone', 'measurements': [{'status': 'observed-tone'}]}}
            with patch.object(m, 'namespace_capture', return_value=fake):
                result = m.action_doctor(root, tools)
            self.assertFalse(result['web_audio_probe']['passed'])
            self.assertFalse(result['web_audio_probe']['checks']['tone_signal_measured'])
            self.assertFalse(result['action_trace_capture']['passed'])

    def test_audio_failure_does_not_discard_action_observation_acceptance(self):
        m = acceptance(self)
        def capture(workspace, source, output, tools, spec, **kwargs):
            if 'audio_probe' in spec:
                raise ValueError('Audio observation unavailable')
            moving = source.stem == 'moving'
            return {'passed': True, 'frames': [{'time_ms': t, 'requested_time_ms': t} for t in m.SAMPLES],
                    'input_events': [{'type': 'click', 'isTrusted': True, 'target': 'choose'}],
                    'dom_samples': [{'elements': [{'selector': '#carrier', 'bounds': {'x': i * 15 if moving else 0}},
                                                 {'selector': '#state', 'text': 'Before' if i < 2 else 'After'}]}
                                    for i in range(len(m.SAMPLES))]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); tools = stage(root)
            with patch.object(m, 'namespace_capture', side_effect=capture):
                result = m.action_doctor(root, tools)
            self.assertTrue(result['action_trace_capture']['passed'], result)
            self.assertFalse(result['web_audio_probe']['passed'])
            self.assertEqual(len(result['web_audio_probe']['failures']), 4)

    def test_unsafe_inputs_cannot_write_through_a_symlink(self):
        m = acceptance(self)
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); root = base / 'workspace'; root.mkdir(); outside = base / 'outside'; outside.mkdir()
            (root / 'inputs').symlink_to(outside, target_is_directory=True)
            with patch.object(m, 'namespace_capture') as capture:
                result = m.action_doctor(root, {})
            self.assertFalse(result['action_trace_capture']['passed'])
            self.assertFalse(result['web_audio_probe']['passed'])
            capture.assert_not_called()
            self.assertEqual(list(outside.iterdir()), [])


@unittest.skipUnless(CHROME.is_file() and Path('/usr/bin/bwrap').is_file(), 'Optional offline Chromium namespace runtimes are unavailable.')
class ActualActionAcceptance(unittest.TestCase):
    def test_real_doctor_promotes_only_observed_motion_trusted_actions_and_measured_audio(self):
        m = acceptance(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); tools = stage(root)
            result = m.action_doctor(root, tools)
            self.assertEqual(result['generation_calls'], 0)
            self.assertTrue(result['action_trace_capture']['passed'], result)
            self.assertTrue(result['web_audio_probe']['passed'], result)
            self.assertTrue(all(result['action_trace_capture']['checks'].values()), result)
            self.assertTrue(all(result['web_audio_probe']['checks'].values()), result)
            for capability in ('action_trace_capture', 'web_audio_probe'):
                self.assertTrue(all((root / e['path']).is_file() for e in result[capability]['evidence']))


if __name__ == '__main__':
    unittest.main()
