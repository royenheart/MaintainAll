"""Independent HTML reopening preserves sealed assets without trusting solver evaluators."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skill_bench.verifier import reopen_visual, reference_assets
from test_review import pixel_png


class VisualVerifierTests(unittest.TestCase):
    def test_independent_geometry_trace_remains_bound_to_its_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); trial = root / 'trials/test'; trial.mkdir(parents=True)
            raw = b'<div id="carrier">Card</div>'; (trial/'source.html').write_bytes(raw)
            source = {'path':'index.html','snapshot':'source.html','sha256':hashlib.sha256(raw).hexdigest(),
                      'size':len(raw),'kind':'editable','format':'html'}
            plan = {'turn':1,'source_artifact':'index.html','scenarios':[
                {'id':'interrupt','spec':{'samples_ms':[0,1000],'trace_samples_ms':[0,250,500,1000],
                                         'profiles':['desktop'],'selectors':['#carrier'],'actions':[]}}]}
            trace = {'profile':'desktop','requested_time_ms':250,'time_ms':251,'sample_completed_ms':253,
                     'elements':[{'selector':'#carrier','bounds':{'x':40,'y':20,'width':90,'height':50}}]}
            def capture(workspace,path,output,tools,**kwargs):
                output.mkdir(); png=pixel_png(20); (output/'frame.png').write_bytes(png)
                result={'passed':True,'source_reopen_verified':True,'source_sha256':source['sha256'],
                        'scope_version':3,'frames':[{'path':'frame.png','sha256':hashlib.sha256(png).hexdigest(),'label':'desktop'}],
                        'trace_samples':[trace]}
                (output/'evidence.json').write_text(json.dumps(result));return result
            with patch('skill_bench.visual_runtime.stage'),patch('skill_bench.browser_namespace.namespace_capture',side_effect=capture):
                proof=reopen_visual(root,'test',source,'renderer',root/'verifier/workspace',{'browser':{}},browser_plan=plan)
            self.assertEqual(proof['playback'].get('trace_samples'),[{**trace,'scenario':'interrupt'}])
            self.assertEqual(proof['playback']['scope_version'],4)
            self.assertEqual(proof['quality_status'],'unassessed')

    def test_frozen_turn_scenarios_replace_generic_replay_and_remain_unscored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); trial = root / 'trials/test'; trial.mkdir(parents=True)
            raw = b'<button id="one">One</button><button id="two">Two</button>'
            (trial / 'source.html').write_bytes(raw)
            source = {'path': 'index.html', 'snapshot': 'source.html', 'sha256': hashlib.sha256(raw).hexdigest(),
                      'size': len(raw), 'kind': 'editable', 'format': 'html'}
            plan = {'turn': 1, 'source_artifact': 'index.html', 'scenarios': [
                {'id': name, 'spec': {'samples_ms': [0, 180, 400], 'profiles': ['desktop'], 'selectors': ['#'+name],
                                     'actions': [{'time_ms': 100, 'type': 'click', 'selector': '#'+name}]}}
                for name in ('one', 'two')]}
            called = []
            def capture(workspace, path, output, tools, **kwargs):
                called.append(kwargs['spec']); output.mkdir()
                png = pixel_png(20); (output / 'frame.png').write_bytes(png)
                result = {'passed': True, 'source_reopen_verified': True, 'source_sha256': source['sha256'],
                          'scope_version': 2, 'frames': [{'path': 'frame.png', 'sha256': hashlib.sha256(png).hexdigest(),
                                                         'label': 'desktop', 'profile': 'desktop', 'time_ms': 180,
                                                         'capture_started_ms': 188, 'capture_completed_ms': 700}],
                          'actions': kwargs['spec']['actions'],
                          'action_snapshots': [{'profile': 'desktop', 'requested_time_ms': 100, 'time_ms': 104,
                                                'elements': [{'selector': '#one', 'x': 49.9}]}],
                          'dom_samples': [{'profile': 'desktop', 'requested_time_ms': 180, 'time_ms': 188}],
                          'input_events': [{'type': 'click', 'isTrusted': True}], 'audio_samples': []}
                (output / 'evidence.json').write_text(json.dumps(result))
                return result
            with patch('skill_bench.visual_runtime.stage'), patch('skill_bench.browser_namespace.namespace_capture', side_effect=capture):
                proof = reopen_visual(root, 'test', source, 'renderer', root / 'verifier/workspace', {'browser': {}},
                                      browser_scenario={'samples_ms': [0, 999]}, browser_plan=plan)
            self.assertEqual(called, [s['spec'] for s in plan['scenarios']])
            self.assertEqual([s['id'] for s in proof['playback']['scenarios']], ['one', 'two'])
            self.assertTrue(proof['playback']['interactions'])
            self.assertEqual(len(proof['rendered']), 2)
            self.assertEqual(proof['quality_status'], 'unassessed')
            self.assertFalse(proof['source_editability_verified'])
            self.assertEqual(proof['playback']['scope_version'], 3)
            self.assertEqual([s['scenario'] for s in proof['playback']['action_snapshots']], ['one', 'two'])
            self.assertEqual(proof['playback']['action_snapshots'][0]['elements'][0]['x'], 49.9)
            self.assertEqual([s['scenario'] for s in proof['playback']['dom_samples']], ['one', 'two'])
            self.assertEqual(proof['playback']['samples'][0]['capture_completed_ms'], 700)
            self.assertEqual(proof['rendered']['frame-1']['capture_started_ms'], 188)

    def test_local_css_js_and_nested_data_are_restored_by_hash_inside_the_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trial = root / 'trials/test'
            trial.mkdir(parents=True)
            inventory = []
            files = {'index.html': b'<link rel="stylesheet" href="assets/style.css"><script src="assets/app.js"></script>',
                     'assets/style.css': b'body{background:blue}',
                     'assets/app.js': b'document.body.dataset.ready="true"',
                     'assets/data.json': b'{"value":1}',
                     'generate.py': b'raise RuntimeError("must not execute")'}
            for name, raw in files.items():
                path = trial / name
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(raw)
                inventory.append({'path': name, 'snapshot': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)})
            source = {**inventory[0], 'kind': 'editable', 'format': 'html'}
            references = []
            for name in ('earlier', 'current', 'future'):
                raw = pixel_png(30)
                (root / (name + '.png')).write_bytes(raw)
                references.append({'id': name, 'path': name + '.png', 'sha256': hashlib.sha256(raw).hexdigest()})
            case = {'assets': references, 'turns': [{'attachments': ['earlier']}, {'attachments': ['current']}, {'attachments': ['future']}]}
            def capture(workspace, path, output, tools, **kwargs):
                for name in ('assets/style.css', 'assets/app.js', 'assets/data.json'):
                    self.assertEqual((workspace / 'inputs' / name).read_bytes(), files[name])
                self.assertFalse((workspace / 'inputs/generate.py').exists())
                self.assertTrue((workspace / 'inputs/inputs/earlier.png').exists())
                self.assertTrue((workspace / 'inputs/inputs/current.png').exists())
                self.assertFalse((workspace / 'inputs/inputs/future.png').exists())
                self.assertIsNone(kwargs['spec'])
                output.mkdir()
                raw = pixel_png(20)
                (output / 'frame.png').write_bytes(raw)
                (output / 'evidence.json').write_text(json.dumps({'passed': True, 'source_reopen_verified': True, 'source_sha256': source['sha256'],
                    'frames': [{'path': 'frame.png', 'sha256': hashlib.sha256(raw).hexdigest()}]}))
            with patch('skill_bench.visual_runtime.stage'), patch('skill_bench.browser_namespace.namespace_capture', side_effect=capture):
                proof = reopen_visual(root, 'test', source, 'renderer', root / 'verifier/workspace', {'browser': {}}, siblings=inventory, assets=reference_assets(case, 2))
            self.assertTrue(proof['source_reopen_verified'])
            self.assertFalse(proof['source_editability_verified'])
            self.assertEqual(proof['execution_scope'], 'sandboxed-html')
            inventory[1]['sha256'] = '0' * 64
            with patch('skill_bench.visual_runtime.stage'), patch('skill_bench.browser_namespace.namespace_capture') as browser:
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    reopen_visual(root, 'test', source, 'renderer', root / 'verifier/tampered', {'browser': {}}, siblings=inventory)
                browser.assert_not_called()
