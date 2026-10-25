"""Bounded dynamic and audio evidence contracts; generated HTML stays in namespaces."""

import importlib
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
DRIVER = SRC / 'skill_bench/browser_driver.py'
from runtime_support import CHROME
FIXTURES = Path(__file__).parent / 'fixtures/browser_action_audio'


def confined_capture(root, fixture, name, spec):
    """Only the trusted namespace broker may execute the authored browser fixture."""
    m = importlib.import_module('skill_bench.browser_namespace')
    if not (root / 'inputs').exists():
        (root / 'inputs').mkdir(); (root / 'tools').mkdir()
        shutil.copyfile(DRIVER, root / 'tools/browser_driver.py')
    source = root / 'inputs' / fixture
    shutil.copyfile(FIXTURES / fixture, source)
    tools = {'browser': {'executable': str(CHROME), 'root': str(CHROME.parent),
                         'driver_sha256': hashlib.sha256(DRIVER.read_bytes()).hexdigest()}}
    return m.namespace_capture(root, source, root / name, tools, spec, timeout=35)


def audio_spec(mode):
    return {'samples_ms': [0, 250, 600, 1000, 1400], 'profiles': ['desktop'], 'selectors': ['#meter', '#state'],
            'audio_probe': {'mode': mode, 'file_input_selector': '#file', 'play_button_selector': '#play'}}


class DynamicSpecContracts(unittest.TestCase):
    def test_independent_geometry_trace_is_bounded_and_optional(self):
        m = importlib.import_module('skill_bench.browser_driver')
        requested = {'samples_ms': [0, 1000], 'selectors': ['#meter'],
                     'trace_samples_ms': list(range(0, 1001, 20))}
        try:
            actual = m.validate_spec(requested)
        except ValueError as exc:
            self.fail(f'Independent bounded trace was rejected: {exc}')
        self.assertEqual(actual['trace_samples_ms'], requested['trace_samples_ms'])
        self.assertNotIn('trace_samples_ms', m.validate_spec())
        for trace in ([], [0, 0], [100, 0], [0, 1001], [0, True], list(range(129))):
            with self.subTest(trace=trace), self.assertRaises(ValueError):
                m.validate_spec({**requested, 'trace_samples_ms': trace})
        with self.assertRaisesRegex(ValueError, 'selector'):
            m.validate_spec({**requested, 'selectors': []})

    def test_dense_fifteen_second_capture_is_supported_without_changing_defaults(self):
        m = importlib.import_module('skill_bench.browser_driver')
        samples = [round(i * 15000 / 47, 3) for i in range(48)]
        try:
            spec = m.validate_spec({'samples_ms': samples, 'profiles': ['desktop']})
        except ValueError as exc:
            self.fail(f'Bounded 48-sample, 15-second capture was rejected: {exc}')
        self.assertEqual(spec['samples_ms'], samples)
        self.assertEqual(m.validate_spec()['samples_ms'], [0, 250, 700])

    def test_sample_and_audio_bounds_reject_code_arbitrary_signal_and_missing_controls(self):
        m = importlib.import_module('skill_bench.browser_driver')
        probe = audio_spec('tone')['audio_probe']
        for invalid in ({'samples_ms': list(range(49))}, {'samples_ms': [0, 15001]},
                        {'audio_probe': {**probe, 'frequency_hz': 1000}}, {'audio_probe': {**probe, 'mode': 'invented'}},
                        {'audio_probe': {**probe, 'mode': []}},
                        {'audio_probe': {'mode': 'tone'}}, {'audio_probe': {**probe, 'script': 'alert(1)'}},
                        {'audio_probe': {**probe, 'file_input_selector': 'x' * 161}}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                m.validate_spec(invalid)

    def test_evaluator_pcm_has_fixed_duration_frequency_and_silent_negative(self):
        m = importlib.import_module('skill_bench.browser_driver')
        self.assertTrue(hasattr(m, 'write_audio_probe'), 'Evaluator-owned PCM generator is absent.')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for mode in ('tone', 'silence', 'unavailable'):
                metadata = m.write_audio_probe(root, mode)
                content = (root / metadata['path']).read_bytes()
                self.assertEqual(metadata['sha256'], hashlib.sha256(content).hexdigest())
                with wave.open(str(root / metadata['path'])) as handle:
                    self.assertEqual((handle.getnchannels(), handle.getsampwidth(), handle.getframerate(), handle.getnframes()), (1, 2, 16000, 272000))
                    values = struct.unpack('<' + 'h' * 16000, handle.readframes(16000))
                self.assertEqual(metadata['frequency_hz'], None if mode == 'silence' else 440)
                if mode == 'silence':
                    self.assertEqual(max(map(abs, values)), 0)
                else:
                    positive_crossings = sum(a <= 0 < b for a, b in zip(values, values[1:]))
                    self.assertEqual(positive_crossings, 440)

    def test_help_explains_conditional_signal_and_quality_limits(self):
        result = subprocess.run([sys.executable, str(DRIVER), '--help'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('audio_probe', result.stdout, 'The conditional audio specification is not documented.')
        self.assertIn('15000', result.stdout)
        self.assertIn('aesthetic', result.stdout)


@unittest.skipUnless(CHROME.is_file() and Path('/usr/bin/bwrap').is_file(), 'Optional offline Chromium namespace runtimes are unavailable.')
class ActualDynamicAudioNamespace(unittest.TestCase):
    def test_pause_resume_is_measured_independently_of_continuing_background_geometry(self):
        with tempfile.TemporaryDirectory() as temporary:
            spec = audio_spec('tone')
            spec.update(samples_ms=[0,250,600,900,1200,1800,2400],selectors=['#carrier'],
                        trace_samples_ms=list(range(0,2401,100)),
                        actions=[{'type':'click','selector':'#toggle','time_ms':700},
                                 {'type':'click','selector':'#toggle','time_ms':1700}])
            result=confined_capture(Path(temporary),'pause.html','pause',spec)
            self.assertTrue(result['passed'],result)
            samples={row['requested_time_ms']:row['media'][0] for row in result['audio_samples']}
            self.assertTrue(samples[600]['playing'],samples)
            self.assertFalse(samples[900]['playing'],samples)
            self.assertFalse(samples[1200]['playing'],samples)
            self.assertAlmostEqual(samples[900]['current_time_seconds'],samples[1200]['current_time_seconds'],delta=.02)
            self.assertTrue(samples[2400]['playing'],samples)
            self.assertGreater(samples[2400]['current_time_seconds'],samples[1200]['current_time_seconds']+.4)
            traces={row['requested_time_ms']:row['elements'][0]['bounds']['x'] for row in result['trace_samples']}
            self.assertGreater(traces[1200],traces[900]+10)

    def test_dense_real_motion_has_actual_times_and_static_claim_has_unchanged_frames(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = {'samples_ms': list(range(0, 2400, 50)), 'profiles': ['desktop'], 'selectors': ['#carrier']}
            moving = confined_capture(root, 'motion.html', 'moving', spec)
            static = confined_capture(root, 'claimed-static.html', 'static', spec)
            for result in (moving, static):
                self.assertTrue(result['passed'], result)
                self.assertEqual(result['scope_version'], 2)
                self.assertEqual(len(result['frames']), 48)
                self.assertEqual([f['requested_time_ms'] for f in result['frames']], spec['samples_ms'])
                self.assertEqual([f['time_ms'] for f in result['frames']], sorted(f['time_ms'] for f in result['frames']))
                self.assertGreater(result['frames'][-1]['time_ms'] - result['frames'][0]['time_ms'], 2100)
                self.assertTrue(all(f['time_ms'] <= f['capture_started_ms'] <= f['capture_completed_ms'] for f in result['frames']))
            self.assertGreater(len({f['sha256'] for f in moving['frames']}), 20)
            self.assertEqual(len({f['sha256'] for f in static['frames']}), 1)

    def test_tone_and_silence_are_independently_measured_after_actual_file_and_play_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for mode in ('tone', 'silence'):
                with self.subTest(mode=mode):
                    result = confined_capture(root, 'audio.html', mode, audio_spec(mode))
                    self.assertTrue(result['passed'], result)
                    probe = result['audio_probe']
                    self.assertEqual(probe['measurements'][0]['status'], 'observed-' + mode)
                    self.assertTrue(probe['file_input_dispatched'])
                    self.assertTrue(probe['play_click_dispatched'])
                    self.assertTrue(any(e['type'] == 'click' and e['isTrusted'] and e['target'] == 'play' for e in result['input_events']))
                    observations = [s for s in result['audio_samples'] if s['media'] and s['media'][0]['playing']]
                    self.assertGreaterEqual(len(observations), 3)
                    self.assertGreater(observations[-1]['media'][0]['current_time_seconds'], observations[0]['media'][0]['current_time_seconds'] + .6)
                    spectra = [s['media'][0]['signal'] for s in observations if s['media'][0]['signal']['status'] == 'measured']
                    self.assertGreaterEqual(len(spectra), 2, result['audio_samples'])
                    if mode == 'tone':
                        self.assertTrue(any(s['peak_frequency_hz'] is not None and abs(s['peak_frequency_hz'] - 440) <= 32 and s['rms'] > .05 for s in spectra), spectra)
                    else:
                        self.assertTrue(all(s['rms'] < .001 for s in spectra), spectra)
                    self.assertEqual(hashlib.sha256((root / mode / probe['stimulus']['path']).read_bytes()).hexdigest(), probe['stimulus']['sha256'])

    def test_evaluator_analysis_fault_exercises_visible_fallback_while_media_still_plays(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = confined_capture(root, 'audio.html', 'unavailable', audio_spec('unavailable'))
            self.assertTrue(result['passed'], result)
            self.assertEqual(result['audio_probe']['analysis_fault']['target'], 'main-world AudioContext.prototype.createAnalyser')
            self.assertTrue(result['audio_probe']['analysis_fault']['installed_before_navigation'])
            final = result['dom_samples'][-1]
            self.assertEqual(next(e['text'] for e in final['elements'] if e['selector'] == '#state'), 'Analysis unavailable: static fallback')
            self.assertTrue(any(s['media'] and s['media'][0]['playing'] for s in result['audio_samples']))
            self.assertEqual(len({next(e['bounds']['width'] for e in s['elements'] if e['selector'] == '#meter') for s in result['dom_samples']}), 1)

    def test_audio_claim_without_playback_remains_unmeasured(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = confined_capture(root, 'claimed-audio.html', 'claim', audio_spec('tone'))
            self.assertTrue(result['passed'], result)
            self.assertTrue(result['audio_probe']['play_click_dispatched'])
            self.assertEqual(result['audio_probe']['measurements'][0]['status'], 'unverified')
            self.assertTrue(all(not s['media'] for s in result['audio_samples']))
            self.assertEqual(len({f['sha256'] for f in result['frames']}), 1)

    def test_nonexistent_audio_selector_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); spec = audio_spec('tone')
            spec['audio_probe']['file_input_selector'] = '#not-present'
            with self.assertRaisesRegex(ValueError, 'Audio file input selector'):
                confined_capture(root, 'audio.html', 'missing', spec)


if __name__ == '__main__':
    unittest.main()
