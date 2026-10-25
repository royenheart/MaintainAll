"""Actual Chromium replay and bounded driver contracts; never call a model."""

import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
DRIVER = SRC / 'skill_bench/browser_driver.py'
from runtime_support import CHROME


def driver(test):
    test.assertTrue(DRIVER.is_file(), 'The actual browser replay driver is missing.')
    return importlib.import_module('skill_bench.browser_driver')


FIXTURE = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{margin:0;background:#fafafa;font:18px sans-serif}#carrier{position:absolute;left:40px;top:100px;width:120px;height:70px;background:#156590;animation:travel 1100ms linear infinite alternate}#mark{position:absolute;right:8px;top:9px;width:20px;height:20px;background:#fa7b21}button{margin:20px;padding:12px}#status{margin:20px}body.selected #status{color:#c60018}body:has(button:focus){outline:3px solid #129060}@keyframes travel{to{transform:translateX(180px)}}@media(max-width:500px){#carrier{width:90px;left:20px}}@media(prefers-reduced-motion:reduce){#carrier{animation:none}}
</style></head><body><button id="select">Choose</button><div id="status">Before</div><div id="carrier"><i id="mark"></i></div><script>document.getElementById('select').addEventListener('click',()=>{document.body.classList.add('selected');document.getElementById('status').textContent='After'});window.getComputedStyle=()=>({color:'spoofed'});Element.prototype.getBoundingClientRect=()=>({x:-999,y:-999,width:-999,height:-999});</script></body></html>'''


class BrowserDriverContracts(unittest.TestCase):
    def test_spec_bounds_reject_unbounded_and_executable_actions(self):
        m = driver(self)
        for invalid in ({'samples_ms': [0] * 25}, {'samples_ms': [0, 90000]},
                        {'actions': [{'type': 'evaluate', 'expression': 'fetch(...)'}]},
                        {'samples_ms': [200, 100]}, {'profiles': ['invented']},
                        {'selectors': ['x' * 1000]}, {'extra': 'unknown'}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                m.validate_spec(invalid)

    def test_missing_browser_never_creates_successful_evidence(self):
        m = driver(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'input.html'; source.write_text(FIXTURE)
            with self.assertRaisesRegex(ValueError, 'browser'):
                m.capture(source, root / 'capture', root / 'missing-browser')
            self.assertFalse((root / 'capture/evidence.json').exists())

    def test_sources_and_outputs_cannot_follow_symlinks_or_parent_traversal(self):
        m = driver(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'input.html'; source.write_text(FIXTURE)
            linked = root / 'linked.html'; linked.symlink_to(source)
            for unsafe in (linked, root / 'subdir/../input.html'):
                with self.subTest(path=unsafe), self.assertRaises(ValueError):
                    m.capture(unsafe, root / 'capture', sys.executable)
            destination = root / 'elsewhere'; destination.mkdir()
            (root / 'linked-output').symlink_to(destination, target_is_directory=True)
            with self.assertRaises(ValueError):
                m.capture(source, root / 'linked-output/capture', sys.executable)

    def test_large_sources_and_existing_output_fail_closed(self):
        m = driver(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'input.html'
            source.write_bytes(b'x' * (m.MAX_SOURCE_BYTES + 1))
            with self.assertRaisesRegex(ValueError, 'limit'):
                m.capture(source, root / 'capture', sys.executable)
            source.write_text(FIXTURE); (root / 'capture').mkdir()
            with self.assertRaisesRegex(ValueError, 'existing'):
                m.capture(source, root / 'capture', sys.executable)

    def test_help_is_standalone_and_explains_scope_and_pipe_transport(self):
        driver(self)
        result = subprocess.run([sys.executable, str(DRIVER), '--help'], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('sampled playback', result.stdout)
        self.assertIn('remote-debugging-pipe', result.stdout)

    def test_executable_that_is_not_a_browser_fails_with_bounded_diagnostics(self):
        m = driver(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'input.html'; source.write_text(FIXTURE)
            result = m.capture(source, root / 'capture', sys.executable, timeout=3)
            self.assertFalse(result['passed'])
            self.assertEqual(result['frames'], [])
            self.assertLessEqual(len(result['failure']), 1000)
            self.assertFalse((root / 'capture/profile').exists())


@unittest.skipUnless(CHROME.is_file(), 'Optional existing Chromium runtime is unavailable.')
class ActualChromiumReplay(unittest.TestCase):
    def test_relative_css_javascript_load_and_missing_files_withhold_reopening(self):
        m = driver(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'input.html'
            source.write_text('<!doctype html><link rel="stylesheet" href="theme.css"><div id="state">Before</div><script src="behavior.js"></script>')
            (root / 'theme.css').write_text('#state{font-size:24px;color:rgb(18,52,86)}')
            (root / 'behavior.js').write_text('document.getElementById("state").textContent="Loaded";')
            specification = {'samples_ms': [0, 120], 'profiles': ['desktop'], 'selectors': ['#state']}
            valid = m.capture(source, root / 'valid', CHROME, specification, timeout=15)
            self.assertTrue(valid['passed'], valid)
            self.assertTrue(valid['source_reopen_verified'])
            state = valid['dom_samples'][0]['elements'][0]
            self.assertEqual(state['text'], 'Loaded')
            self.assertEqual(state['computed']['fontSize'], '24px')
            for name in ('theme.css', 'behavior.js'):
                original = (root / name).read_bytes(); (root / name).unlink()
                missing = m.capture(source, root / ('missing-' + name), CHROME, specification, timeout=15)
                self.assertFalse(missing['passed'], missing)
                self.assertFalse(missing['source_reopen_verified'])
                self.assertTrue(any(item['local'] and name in item['url'] for item in missing['resource_failures']))
                (root / name).write_bytes(original)
            (root / 'behavior.js').write_text('const = invalid;')
            broken_script = m.capture(source, root / 'broken-script', CHROME, specification, timeout=15)
            self.assertFalse(broken_script['source_reopen_verified'])
            self.assertTrue(broken_script['runtime_errors'])

    def test_blocked_external_resource_is_distinct_from_missing_local_assets(self):
        m = driver(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'input.html'
            source.write_text('<!doctype html><p>Offline capture</p><img src="https://example.invalid/not-fetched.png">')
            result = m.capture(source, root / 'capture', CHROME, {'samples_ms': [0, 100], 'profiles': ['desktop']}, timeout=15)
            self.assertTrue(result['passed'], result)
            self.assertFalse(result['source_reopen_verified'])
            self.assertTrue(any(item['blocked_external'] and not item['local'] for item in result['resource_failures']))
            self.assertFalse(result['interactions'])

    def test_real_temporal_frames_trusted_input_responsive_and_reduced_motion(self):
        m = driver(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'input.html'; source.write_text(FIXTURE)
            specification = {'samples_ms': [0, 180, 520], 'selectors': ['#carrier', '#mark', '#status', '#select'],
                             'actions': [{'time_ms': 100, 'type': 'click', 'selector': '#select'},
                                         {'time_ms': 300, 'type': 'key', 'key': 'Tab'}]}
            result = m.capture(source, root / 'capture', CHROME, specification, timeout=35)
            self.assertTrue(result['passed'], result)
            self.assertEqual(result['source_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual((root / 'capture/source.html').read_bytes(), source.read_bytes())
            self.assertEqual(len(result['frames']), 9)
            self.assertEqual({tuple(f['viewport']) for f in result['frames']}, {(1280, 800), (390, 844)})
            self.assertTrue(result['interactions'])
            self.assertTrue(any(e['isTrusted'] and e['type'] == 'click' for e in result['input_events']))
            by_profile = {name: [f for f in result['frames'] if f['profile'] == name] for name in m.PROFILES}
            self.assertNotEqual(by_profile['desktop'][0]['sha256'], by_profile['desktop'][1]['sha256'])
            for profile, frames in by_profile.items():
                self.assertEqual([f['time_ms'] for f in frames], sorted(f['time_ms'] for f in frames))
                for frame in frames:
                    png = root / 'capture' / frame['path']
                    self.assertEqual(hashlib.sha256(png.read_bytes()).hexdigest(), frame['sha256'])
                    self.assertEqual(m.png_dimensions(png.read_bytes()), tuple(frame['viewport']))
                samples = [s for s in result['dom_samples'] if s['profile'] == profile]
                carrier = next(e for e in samples[0]['elements'] if e['selector'] == '#carrier')
                self.assertGreaterEqual(carrier['bounds']['x'], 0, 'Main-world prototype spoofing must not replace trusted diagnostics.')
                self.assertNotEqual(carrier['computed']['color'], 'spoofed')
                self.assertEqual(next(e for e in samples[0]['elements'] if e['selector'] == '#status')['text'], 'Before')
                self.assertEqual(next(e for e in samples[-1]['elements'] if e['selector'] == '#status')['text'], 'After')
            mobile = next(s for s in result['dom_samples'] if s['profile'] == 'mobile')
            desktop = next(s for s in result['dom_samples'] if s['profile'] == 'desktop')
            self.assertLess(next(e for e in mobile['elements'] if e['selector'] == '#carrier')['bounds']['width'], next(e for e in desktop['elements'] if e['selector'] == '#carrier')['bounds']['width'])
            reduced = [s for s in result['dom_samples'] if s['profile'] == 'reduced_motion']
            self.assertTrue(all(s['reduced_motion'] for s in reduced))
            self.assertEqual(len({next(e for e in s['elements'] if e['selector'] == '#carrier')['computed']['transform'] for s in reduced}), 1)
            self.assertFalse((root / 'capture/profile').exists())
            self.assertEqual(result['transport'], 'remote-debugging-pipe')


if __name__ == '__main__':
    unittest.main()
