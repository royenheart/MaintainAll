"""Frozen action plans are task data, never solver-owned verification code."""
import copy
import tempfile
import unittest
from pathlib import Path

from skill_bench.contracts import validate_case


def case():
    return {
        'schema_version': 2, 'id': 'action-case', 'version': 1,
        'family': 'browser', 'split': 'development', 'assets': [],
        'turns': [{'id': 't1', 'prompt': 'Show a selectable moving panel.', 'attachments': [],
                   'artifacts': [{'path': 'index.html', 'kind': 'editable', 'format': 'html'},
                                 {'path': 'frame.png', 'kind': 'preview', 'format': 'png'}]}],
        'requirements': [{'id': 'selection', 'turn': 1, 'quote': 'selectable moving panel'}],
        'atoms': [{'id': 'selection', 'dimension': 'ownership', 'criterion': 'Selection changes the panel.',
                   'requirement_ids': ['selection'], 'active_turns': [1], 'depends_on': [],
                   'anchors': {'0': 'Absent', '1': 'Partial', '2': 'Supported'},
                   'evidence': {'kind': 'trace', 'required_artifacts': ['index.html', 'frame.png']}}],
        'capabilities': ['browser_capture', 'action_trace_capture'],
        'limits': {'turn_seconds': 30, 'max_file_bytes': 1024, 'max_workspace_bytes': 4096},
        'provenance': {},
    }


def plan():
    return {'turn': 1, 'source_artifact': 'index.html', 'scenarios': [
        {'id': 'select', 'spec': {'profiles': ['desktop'], 'samples_ms': [0, 180, 400],
                               'selectors': ['#select', '#panel'],
                               'actions': [{'time_ms': 100, 'type': 'click', 'selector': '#select'}]}}
    ]}


class ActionPlanContracts(unittest.TestCase):
    def check(self, value):
        with tempfile.TemporaryDirectory() as tmp:
            return validate_case(value, Path(tmp), Path(tmp))

    def test_action_capability_requires_a_frozen_task_observation_plan(self):
        with self.assertRaisesRegex(ValueError, 'observation plan'):
            self.check(case())

    def test_valid_plan_is_task_bound_and_legacy_cases_stay_compatible(self):
        value = case()
        value['provenance']['observation_plans'] = [plan()]
        self.assertEqual(self.check(value), value)
        value['capabilities'].remove('action_trace_capture')
        value['provenance'] = {}
        self.assertEqual(self.check(value), value)

    def test_no_code_missing_sources_future_turns_or_empty_actions(self):
        for mutation in ('code', 'source', 'future', 'actions'):
            value = case(); p = plan()
            if mutation == 'code': p['scenarios'][0]['spec']['script'] = 'alert(1)'
            if mutation == 'source': p['source_artifact'] = 'undeclared.html'
            if mutation == 'future': p['turn'] = 2
            if mutation == 'actions': p['scenarios'][0]['spec']['actions'] = []
            value['provenance']['observation_plans'] = [p]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.check(value)

    def test_audio_capability_requires_all_three_frozen_conditions(self):
        value = case(); value['capabilities'].append('web_audio_probe')
        p = plan(); p['scenarios'][0]['spec']['audio_probe'] = {
            'mode': 'tone', 'file_input_selector': '#audio-file', 'play_button_selector': '#play'}
        value['provenance']['observation_plans'] = [p]
        with self.assertRaisesRegex(ValueError, 'audio.*conditions'):
            self.check(value)


if __name__ == '__main__':
    unittest.main()
