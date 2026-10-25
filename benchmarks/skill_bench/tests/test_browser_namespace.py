"""Native browser namespace confinement; authored fixtures, no model calls."""

import hashlib
import os
import importlib
import base64
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))
from runtime_support import CHROME
MODULE = SRC / 'skill_bench/browser_namespace.py'


def module(test):
    test.assertTrue(MODULE.is_file(), 'The confined host browser namespace is missing.')
    return importlib.import_module('skill_bench.browser_namespace')


def fixture(root):
    (root / 'inputs').mkdir(); (root / 'tools').mkdir()
    driver = SRC / 'skill_bench/browser_driver.py'
    shutil.copyfile(driver, root / 'tools/browser_driver.py')
    source = root / 'inputs/source.html'
    source.write_text('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>div{width:80px;height:50px;background:#086;animation:m .8s linear infinite alternate}@keyframes m{to{transform:translateX(100px)}}@media(prefers-reduced-motion:reduce){div{animation:none}}</style><div></div><button id="choose" onclick="this.textContent=\'Chosen\'">Choose</button>')
    tools = {'browser': {'executable': str(CHROME), 'root': str(CHROME.parent), 'driver_sha256': hashlib.sha256(driver.read_bytes()).hexdigest()}}
    return source, tools


class BrowserNamespaceContracts(unittest.TestCase):
    def setUp(self):
        m = module(self)
        self.real_identity = m.fingerprint_identity
        identity = mock.patch.object(m, 'fingerprint_identity', return_value={})
        identity.start()
        self.addCleanup(identity.stop)

    def test_only_explicit_evaluator_capture_tree_is_excluded_from_frozen_inputs(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'workspace'; root.mkdir()
            source, _ = fixture(root)
            (root / 'captures').mkdir()
            (root / 'captures/old.png').write_bytes(b'previous evaluator output')
            descriptor = os.open(root, m.DIRECTORY_FLAGS)
            try:
                frozen = Path(temporary) / 'frozen'
                counts = m.freeze_workspace(descriptor, frozen, exclude_top_level=('captures',))
                self.assertFalse((frozen / 'captures').exists())
                self.assertEqual((frozen / 'inputs/source.html').read_bytes(), source.read_bytes())
                self.assertTrue((frozen / 'tools/browser_driver.py').is_file())
                self.assertEqual(counts['excluded_top_level'], ['captures'])
                for forbidden in ('tools', 'inputs', '../captures', 'captures/old.png', ''):
                    with self.subTest(forbidden=forbidden), self.assertRaises(ValueError):
                        m.freeze_workspace(descriptor, Path(temporary) / ('bad-' + str(len(forbidden))), exclude_top_level=(forbidden,))
                normal = Path(temporary) / 'normal'
                m.freeze_workspace(descriptor, normal)
                self.assertTrue((normal / 'captures/old.png').is_file())
            finally:
                os.close(descriptor)

    def test_too_short_deadline_is_rejected_before_launch(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source, tools = fixture(root)
            with mock.patch.object(m.subprocess, 'Popen') as launch:
                with self.assertRaisesRegex(ValueError, 'between 6 and 120'):
                    m.namespace_capture(root, source, root / 'evidence', tools, timeout=5)
                launch.assert_not_called()
            self.assertFalse((root / 'evidence').exists())

    def test_missing_bwrap_never_falls_back_to_host_browser(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source, tools = fixture(root)
            with mock.patch.object(m, 'fingerprint_identity', self.real_identity), mock.patch.object(m, 'BWRAP', root / 'missing-bwrap'), mock.patch.object(m.subprocess, 'Popen') as launch:
                with self.assertRaisesRegex(ValueError, 'namespace runtime'):
                    m.namespace_capture(root, source, root / 'evidence', tools)
                launch.assert_not_called()
            self.assertFalse((root / 'evidence').exists())

    def test_output_and_source_escape_symlinks_and_hardlinks_fail_closed(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); root = base / 'workspace'; root.mkdir(); source, tools = fixture(root)
            runtime = base / 'runtime'; runtime.mkdir()
            executable = runtime / 'chrome'
            executable.write_text('#!/bin/sh\nexit 99\n')
            executable.chmod(0o700)
            tools['browser'].update(executable=str(executable), root=str(runtime))
            outside = base / 'outside'; outside.mkdir()
            (root / 'linked').symlink_to(outside, target_is_directory=True)
            for output in (outside / 'capture', root / 'linked/capture', root / 'x/../capture'):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    m.namespace_capture(root, source, output, tools)
            self.assertEqual(list(outside.iterdir()), [])
            (root / 'linked').unlink()
            (root / 'hardlink.html').hardlink_to(source)
            with mock.patch.object(m, 'run') as launch:
                with self.assertRaisesRegex(ValueError, 'hard link'):
                    m.namespace_capture(root, source, root / 'evidence', tools)
                launch.assert_not_called()


@unittest.skipUnless(CHROME.is_file() and Path('/usr/bin/bwrap').is_file(), 'Optional native browser namespace runtimes are unavailable.')
class ActualBrowserNamespace(unittest.TestCase):
    def test_successive_evaluator_scenarios_do_not_read_prior_capture_outputs(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source, tools = fixture(root)
            (root / 'captures').mkdir()
            original = source.read_bytes()
            spec = {'samples_ms': [0, 180, 400], 'profiles': ['desktop'],
                    'actions': [{'time_ms': 100, 'type': 'click', 'selector': '#choose'}]}
            results = [m.namespace_capture(root, source, root / 'captures' / name, tools, spec,
                                          timeout=20, exclude_top_level=('captures',)) for name in ('first', 'second')]
            self.assertEqual(results[0]['namespace']['frozen_workspace'], results[1]['namespace']['frozen_workspace'])
            self.assertEqual(results[0]['source_sha256'], results[1]['source_sha256'])
            self.assertEqual(source.read_bytes(), original)
            self.assertTrue(all(row['namespace']['resource_boundary']['passed'] for row in results))
            self.assertTrue((root / 'captures/first/evidence.json').is_file())
            self.assertTrue((root / 'captures/second/evidence.json').is_file())

    def test_actual_namespace_denies_host_network_credentials_and_input_writes(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source, tools = fixture(root)
            original = source.read_bytes()
            image = root / 'inputs/reference.png'
            image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jR2UAAAAASUVORK5CYII='))
            source.write_text(source.read_text() + '<img id="reference" src="reference.png">')
            original = source.read_bytes()
            proof = m.namespace_doctor(root, tools)
            self.assertTrue(proof['passed'], proof)
            self.assertTrue(proof['checks']['network_denied'])
            self.assertTrue(proof['checks']['host_loopback_denied'])
            self.assertTrue(proof['checks']['udp_denied'])
            self.assertTrue(proof['checks']['host_credentials_denied'])
            self.assertTrue(proof['checks']['host_marker_denied'])
            self.assertTrue(proof['checks']['source_readonly'])
            self.assertTrue(proof['checks']['tools_readonly'])
            self.assertTrue(proof['checks']['output_writable'])
            self.assertTrue(proof['checks']['unix_socketpair_available'])
            result = m.namespace_capture(root, source, root / 'nested/evidence', tools,
                {'samples_ms': [0, 200, 600], 'actions': [{'time_ms': 100, 'type': 'click', 'selector': '#choose'}]}, timeout=40)
            self.assertTrue(result['passed'], result)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(result['source_sha256'], hashlib.sha256(original).hexdigest())
            self.assertTrue(result['interactions'])
            self.assertEqual(len(result['frames']), 9)
            reference = next(e for e in result['dom_samples'][0]['elements'] if e['selector'] == '#reference')
            self.assertTrue(reference['image']['complete'])
            self.assertEqual(reference['image']['natural_width'], 1)
            self.assertGreater(len({f['sha256'] for f in result['frames']}), 1)
            self.assertEqual(result['namespace']['method'], 'bubblewrap-unshare-all')
            self.assertFalse((root / 'nested/evidence/profile').exists())
            self.assertEqual({p.name for p in root.iterdir()}, {'inputs', 'tools', 'nested'})

    def test_changed_output_parent_cannot_redirect_host_publication(self):
        m = module(self)
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary); root = base / 'workspace'; root.mkdir(); source, tools = fixture(root)
            outside = base / 'outside'; outside.mkdir(); (root / 'nested').mkdir()
            original_run = m.run
            def replace_parent(*args, **kwargs):
                result = original_run(*args, **kwargs)
                (root / 'nested').rename(root / 'old-nested')
                (root / 'nested').symlink_to(outside, target_is_directory=True)
                return result
            with mock.patch.object(m, 'run', side_effect=replace_parent):
                with self.assertRaises(ValueError):
                    m.namespace_capture(root, source, root / 'nested/evidence', tools,
                                        {'samples_ms': [0, 100], 'profiles': ['desktop']}, timeout=20)
            self.assertEqual(list(outside.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
