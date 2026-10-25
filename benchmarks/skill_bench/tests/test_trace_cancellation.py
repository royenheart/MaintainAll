"""Deterministic cancellation at the independent geometry action barrier."""
from pathlib import Path
import threading
import types
import unittest
from unittest.mock import patch

from skill_bench import browser_driver as driver


class TraceCancellation(unittest.TestCase):
    def test_failed_main_capture_cancels_trace_waiting_for_an_undispatched_action(self):
        waiting = threading.Event()
        writes = {}

        class MemoryOutput:
            def __init__(self, name='memory-output'): self.name = name
            def __truediv__(self, name): return MemoryOutput(self.name + '/' + name)
            @property
            def parent(self): return self
            def is_dir(self): return True
            def exists(self): return False
            def mkdir(self, **kwargs): pass
            def write_bytes(self, data): writes[self.name] = data
            def write_text(self, data, **kwargs): writes[self.name] = data

        class StopEvent:
            def __init__(self): self.event = threading.Event()
            def set(self): self.event.set()
            def is_set(self): return self.event.is_set()
            def wait(self, timeout=None):
                if 'perform_actions' in threading.current_thread().name:
                    return self.event.wait()
                return self.event.wait(timeout)

        class ObservedCondition(threading.Condition):
            def wait(self, timeout=None):
                if 'perform_trace' in threading.current_thread().name:
                    waiting.set()
                return super().wait(timeout)

        class Browser:
            def __init__(self, browser, output, deadline):
                self.deadline = deadline
                self.resource_failures = []
                self.resource_tracking_truncated = False
                self.events = []
                self.stderr = b''
            def command(self, method, *args, **kwargs):
                return {'targetId':'target', 'sessionId':'session', 'frameId':'frame', 'executionContextId':1}
            def close(self): pass

        def fail_diagnostics(*args):
            self.assertTrue(waiting.wait(1), 'Trace must reach the action barrier before cancellation')
            raise RuntimeError('Synthetic screenshot-path diagnostics failure')

        thread_api = types.SimpleNamespace(Thread=threading.Thread, Condition=ObservedCondition, Event=StopEvent)
        source = Path(__file__).parent / 'fixtures/browser_action_audio/pause.html'
        with patch.object(driver, 'safe_path', side_effect=lambda p, **kwargs: p), patch.object(driver, 'PipeBrowser', Browser), patch.object(driver, 'threading', thread_api), patch.object(driver, 'evaluate', return_value='complete'), patch.object(driver, 'diagnostics', side_effect=fail_diagnostics), patch.object(driver.shutil, 'rmtree'):
            result = driver.capture(source, MemoryOutput(), Path('/usr/bin/true'),
                {'samples_ms':[0,10], 'profiles':['desktop'], 'selectors':['#carrier'],
                 'actions':[{'type':'click','selector':'#toggle','time_ms':1}], 'trace_samples_ms':[1,10]}, timeout=3)
            live = [t for t in threading.enumerate() if 'perform_trace' in t.name]
            for thread in live:
                thread.join(2)
        self.assertFalse(result['passed'])
        self.assertIn('Synthetic screenshot-path', result['failure'])
        self.assertTrue(any(path.endswith('/evidence.json') for path in writes))
        self.assertEqual([thread.name for thread in live], [], 'capture returned with a live trace worker')
