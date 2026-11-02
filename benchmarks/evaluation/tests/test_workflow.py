import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eval_framework.workflow import Event, WorkflowError, append, from_jsonl, project, to_jsonl


def ev(seq, typ):
    return Event(typ, seq, 't', {})


def test_projection():
    events = [ev(1, 'calibration.passed'), ev(2, 'trial.started'), ev(3, 'trial.finished'), ev(4, 'grade.recorded'), ev(5, 'review.recorded')]
    assert project(events)['state'] == 'reviewed'
    events = append(events, ev(6, 'record.sealed'))
    assert project(events)['state'] == 'sealed'
    assert from_jsonl(to_jsonl(events)) == events


def test_invalid():
    try:
        append([], ev(1, 'grade.recorded'))
    except WorkflowError:
        pass
    else:
        raise AssertionError('expected invalid transition')
    graded = [ev(1, 'trial.started'), ev(2, 'trial.finished')]
    try:
        append(graded, ev(3, 'review.recorded'))
    except WorkflowError:
        pass
    else:
        raise AssertionError('review must not bypass grade')


if __name__ == '__main__':
    test_projection(); test_invalid(); print('workflow PASS')
