import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eval_framework.contracts import Attempt, Record, RunManifest, sha256


def manifest():
    return RunManifest(run_id='r1', suite='dsh-skills', case='c1', arm='with',
                       workflow_sha256='a' * 64, prompt_sha256='b' * 64,
                       skill_sha256='c' * 64, agent_runtime='dsh', model='m',
                       provider='p', source='test')


def test_roundtrip():
    record = Record(record_id='r1', manifest=manifest(), state='sealed',
                    attempts=(Attempt('a1', 't1', 'scored', 3, 4),),
                    metrics={'mean': 0.75}).with_hash()
    record.validate()
    assert len(record.record_hash) == 64
    clone = Record(**record.__dict__).with_hash()
    assert clone.record_hash == record.record_hash


def test_rejects_bad_attempt():
    try:
        Attempt('a1', 't1', 'scored', 5, 4).validate()
    except ValueError:
        pass
    else:
        raise AssertionError('expected reward > max to fail')


if __name__ == '__main__':
    test_roundtrip(); test_rejects_bad_attempt(); print('contracts PASS')
