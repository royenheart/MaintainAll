"""Validate evaluator-owned browser plans bound to frozen task turns."""
import copy
import re

from .browser_driver import validate_spec


def validate_plans(case):
    capabilities = set(case.get('capabilities', []))
    required = bool(capabilities & {'action_trace_capture', 'web_audio_probe'})
    plans = case.get('provenance', {}).get('observation_plans')
    if plans is None:
        if required:
            raise ValueError('A frozen observation plan is required for action/audio evidence')
        return []
    if not isinstance(plans, list) or not 1 <= len(plans) <= len(case['turns']):
        raise ValueError('Invalid observation plan turn inventory')
    normalized, seen, audio_modes = [], set(), set()
    for plan in plans:
        if not isinstance(plan, dict) or set(plan) != {'turn', 'source_artifact', 'scenarios'}:
            raise ValueError('Observation plans accept only turn, source_artifact and scenarios')
        turn = plan['turn']
        if type(turn) is not int or not 1 <= turn <= len(case['turns']) or turn in seen:
            raise ValueError('Observation plan refers to a future or duplicate turn')
        seen.add(turn)
        sources = {a['path'] for a in case['turns'][turn-1]['artifacts']
                   if a['kind'] == 'editable' and a['format'] == 'html'}
        if plan['source_artifact'] not in sources:
            raise ValueError('Observation plan source must be declared editable HTML for its turn')
        scenarios = plan['scenarios']
        if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 4:
            raise ValueError('Observation plan requires one to four bounded scenarios')
        identifiers, normalized_scenarios = set(), []
        for scenario in scenarios:
            if not isinstance(scenario, dict) or set(scenario) != {'id', 'spec'}:
                raise ValueError('Observation scenarios accept only id and declarative spec')
            identifier = scenario['id']
            if not isinstance(identifier, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}', identifier) or identifier in identifiers:
                raise ValueError('Unsafe or duplicate observation scenario identity')
            identifiers.add(identifier)
            spec = validate_spec(scenario['spec'])
            if not spec['actions'] and not spec.get('audio_probe'):
                raise ValueError('An observation plan must exercise actual input actions')
            for action in spec['actions']:
                if not any(t < action['time_ms'] for t in spec['samples_ms']) or not any(t > action['time_ms'] for t in spec['samples_ms']):
                    raise ValueError('Observation samples must bracket each declared input action')
            if spec.get('audio_probe'):
                audio_modes.add(spec['audio_probe']['mode'])
            normalized_scenarios.append({'id': identifier, 'spec': spec})
        normalized.append({**plan, 'scenarios': normalized_scenarios})
    if required and seen != set(range(1, len(case['turns']) + 1)):
        raise ValueError('An observation plan is required for every applicable turn')
    if 'web_audio_probe' in capabilities and audio_modes != {'tone', 'silence', 'unavailable'}:
        raise ValueError('Controlled audio observation conditions must include tone, silence and unavailable')
    return sorted(normalized, key=lambda p: p['turn'])


def plan_for_turn(case, turn):
    return next((copy.deepcopy(p) for p in validate_plans(case) if p['turn'] == turn), None)
