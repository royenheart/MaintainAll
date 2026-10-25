"""A solver capture request cannot select host programs or escape its workspace."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from skill_bench.browser_broker import BrowserBroker


class BrowserBrokerTests(unittest.TestCase):
    def test_response_is_not_visible_until_all_json_bytes_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text('<p>Capture</p>')
            broker = BrowserBroker(root, {})
            self.addCleanup(broker.close)
            self.request(broker, {'source': 'index.html', 'output': 'capture'})
            original = json.dump
            def writing(value, stream):
                self.assertEqual(list(broker.queue.glob('response-*.json')), [])
                original(value, stream)
                stream.flush()
                self.assertEqual(list(broker.queue.glob('response-*.json')), [])
            with patch('skill_bench.browser_namespace.namespace_capture', return_value={'passed': True, 'frames': [{}, {}]}), patch('skill_bench.browser_broker.json.dump', side_effect=writing):
                broker.service(time.monotonic() + 60)
            response = next(broker.queue.glob('response-*.json'))
            self.assertTrue(json.loads(response.read_text())['passed'])
            self.assertEqual(response.stat().st_nlink, 1)
            self.assertEqual(list(broker.queue.glob('*.pending')), [])

    def request(self, broker, data):
        name = 'request-' + 'a' * 32 + '.json'
        (broker.queue / name).write_text(json.dumps(data))

    def test_literal_capture_request_reaches_only_the_sealed_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text('<button>Choose</button>')
            tools = {'browser': {'executable': '/sealed/runtime/chrome'}}
            broker = BrowserBroker(root, tools)
            self.addCleanup(broker.close)
            self.request(broker, {'source': 'index.html', 'output': 'capture'})
            with patch('skill_bench.browser_namespace.namespace_capture', return_value={'passed': True, 'frames': [{}, {}], 'scope': 'sampled playback'}) as capture:
                broker.service(time.monotonic() + 60)
                broker.service(time.monotonic() + 60)
            self.assertEqual(capture.call_count, 1)
            self.assertEqual(capture.call_args.args[:4], (root, root / 'index.html', root / 'capture', tools))

    def test_untrusted_commands_output_escape_and_source_links_never_launch(self):
        for data in ({'source': 'index.html', 'output': 'capture', 'command': 'cat /host/auth'},
                     {'source': '../auth.json', 'output': 'capture'},
                     {'source': 'index.html', 'output': '../outside'},
                     {'source': 'index.html', 'output': 'inputs/capture'}):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'index.html').write_text('<p>Private test.</p>')
                (root / 'inputs').mkdir()
                broker = BrowserBroker(root, {})
                self.addCleanup(broker.close)
                self.request(broker, data)
                with patch('skill_bench.browser_namespace.namespace_capture') as capture:
                    broker.service(time.monotonic() + 60)
                    capture.assert_not_called()
                response = json.loads(next(broker.queue.glob('response-*.json')).read_text())
                self.assertFalse(response['passed'])

    def test_request_and_response_symlinks_cannot_redirect_host_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = BrowserBroker(root, {})
            self.addCleanup(broker.close)
            outside = root / 'outside'
            outside.write_text('Host canary')
            (broker.queue / ('request-' + 'a' * 32 + '.json')).symlink_to(outside)
            with self.assertRaises(OSError):
                # Response is still confined; malformed source cannot be executed.
                (broker.queue / ('response-' + 'a' * 32 + '.json')).symlink_to(outside)
                broker.service(time.monotonic() + 60)
            self.assertEqual(outside.read_text(), 'Host canary')

    def test_request_count_ceiling_is_enforced_before_namespace_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = BrowserBroker(root, {}, maximum=1)
            self.addCleanup(broker.close)
            for char in 'ab':
                (broker.queue / ('request-' + char * 32 + '.json')).write_text('{}')
            with patch('skill_bench.browser_namespace.namespace_capture') as capture:
                with self.assertRaisesRegex(ValueError, 'ceiling'):
                    broker.service(time.monotonic() + 60)
                capture.assert_not_called()
