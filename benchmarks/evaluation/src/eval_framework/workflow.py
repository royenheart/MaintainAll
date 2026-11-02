"""Pure workflow projection over an append-only event log.

This is a small, data-only analogue of the migrate-bot statechart, not a full engine.
Adapters append events; the projection is a pure function of the log.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json


@dataclass(frozen=True)
class Event:
    type: str
    seq: int
    time: str
    data: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {'type': self.type, 'seq': self.seq, 'time': self.time, 'data': self.data}


TERMINAL = {'sealed', 'failed'}
TRANSITIONS = {
    ('planned', 'calibration.passed'): 'calibrated',
    ('calibrated', 'trial.started'): 'running',
    ('planned', 'trial.started'): 'running',
    ('running', 'trial.started'): 'running',
    ('running', 'trial.finished'): 'evaluated',
    ('evaluated', 'trial.started'): 'running',
    ('evaluated', 'grade.recorded'): 'graded',
    ('graded', 'review.recorded'): 'reviewed',
    ('graded', 'record.sealed'): 'sealed',
    ('reviewed', 'record.sealed'): 'sealed',
}
FAILURE = 'run.failed'


class WorkflowError(ValueError):
    pass


def append(events: list[Event], event: Event) -> list[Event]:
    """Validate one transition; never mutates the input list."""
    state = project(events)['state']
    if state in TERMINAL and event.type != FAILURE:
        raise WorkflowError(f'{state} is terminal')
    if event.type != FAILURE and (state, event.type) not in TRANSITIONS:
        raise WorkflowError(f'invalid transition {state} -> {event.type}')
    return [*events, event]


def project(events: list[Event]) -> dict:
    """Replay a log into its derived state. Unknown/duplicate seq is an error."""
    state = 'planned'
    seen = set()
    attempts = 0
    for event in events:
        if event.seq in seen:
            raise WorkflowError(f'duplicate event seq {event.seq}')
        seen.add(event.seq)
        if event.type == FAILURE:
            state = 'failed'
            continue
        if state in TERMINAL:
            raise WorkflowError(f'event after terminal state: {event.type}')
        nxt = TRANSITIONS.get((state, event.type))
        if nxt is None:
            raise WorkflowError(f'invalid transition {state} -> {event.type}')
        state = nxt
        if event.type == 'trial.finished':
            attempts += 1
    return {'state': state, 'events': len(events), 'attempts': attempts}


def to_jsonl(events: list[Event]) -> str:
    return '\n'.join(json.dumps(event.as_dict(), ensure_ascii=False, sort_keys=True) for event in events) + ('\n' if events else '')


def from_jsonl(text: str) -> list[Event]:
    events = []
    for line in text.splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        events.append(Event(type=raw['type'], seq=int(raw['seq']), time=raw['time'], data=raw.get('data') or {}))
    return events
