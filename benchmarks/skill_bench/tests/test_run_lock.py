"""A concurrent launch cannot replace the winning run's real evidence."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from threading import Event, Lock
import unittest
from unittest.mock import patch

import test_runner as fixtures
from skill_bench.experiment import prepare_experiment
from skill_bench.runner import run_experiment
from skill_bench.store import read_events


class RunLockTests(unittest.TestCase):
    setUp = fixtures.RunnerTests.setUp

    def test_linked_or_special_lock_is_rejected_before_doctor(self):
        sentinel = self.root / 'outside-lock-target'
        sentinel.write_bytes(b'unchanged outside file')
        for kind in ('symlink', 'hardlink', 'fifo'):
            with self.subTest(kind=kind):
                root = self.root / kind
                with patch('skill_bench.experiment.backend', return_value=self.adapter):
                    prepare_experiment(self.root / 'suite.json', root, arms={'none': None}, max_calls=2)
                lock = root / '.run.lock'
                if kind == 'symlink':
                    lock.symlink_to(sentinel)
                elif kind == 'hardlink':
                    os.link(sentinel, lock)
                else:
                    os.mkfifo(lock)
                with patch.object(self.adapter, 'doctor', return_value={'passed': True, 'model_called': False}) as doctor:
                    with self.assertRaisesRegex(ValueError, 'lock'):
                        run_experiment(root, execute=True, adapter=self.adapter)
                    doctor.assert_not_called()
                self.assertEqual(sentinel.read_bytes(), b'unchanged outside file')

    def test_concurrent_launch_is_rejected_before_doctor_or_trial_writes(self):
        first_doctor, second_decision = Event(), Event()
        release_first, release_second, reserved, finish_trial = (Event() for _ in range(4))
        count_lock = Lock()
        doctors = []

        def doctor(config):
            with count_lock:
                number = len(doctors) + 1
                doctors.append(number)
            if number == 1:
                first_doctor.set()
                if not release_first.wait(3):
                    raise AssertionError('First doctor was not released')
            else:
                second_decision.set()
                if not release_second.wait(3):
                    raise AssertionError('Second doctor was not released')
            return {'passed': True, 'model_called': False}

        original = self.adapter.execute_trial

        def execute(spec, output, emit):
            def delayed_emit(event):
                emit(event)
                if event['type'] == 'call_reserved' and event['turn'] == 1:
                    reserved.set()
                    if not finish_trial.wait(3):
                        raise AssertionError('First trial was not released')
            return original(spec, output, delayed_emit)

        self.adapter.doctor = doctor
        self.adapter.execute_trial = execute
        root = self.root / 'run'

        def attempt():
            try:
                return run_experiment(root, execute=True, adapter=self.adapter)
            except Exception as error:
                return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(attempt)
            self.assertTrue(first_doctor.wait(3))
            second = pool.submit(attempt)
            second.add_done_callback(lambda _: second_decision.set())
            try:
                self.assertTrue(second_decision.wait(3))
                release_first.set()
                self.assertTrue(reserved.wait(3))
                release_second.set()
                second_result = second.result(timeout=3)
            finally:
                release_first.set()
                release_second.set()
                finish_trial.set()
            first_result = first.result(timeout=3)

        self.assertIsInstance(second_result, ValueError)
        self.assertIn('executing', str(second_result))
        self.assertNotIsInstance(first_result, Exception)
        self.assertEqual(doctors, [1])
        recorded = json.loads((root / 'trials/example--r001--none/result.json').read_text())
        self.assertEqual(len(recorded['turns']), 2)
        self.assertEqual(self.adapter.calls, 2)
        events = read_events(root)
        self.assertEqual(sum(e['type'] == 'run_started' for e in events), 1)
        self.assertEqual(sum(e['type'] == 'call_reserved' for e in events), 2)
        self.assertEqual(sum(e['type'] == 'run_finished' for e in events), 1)
