import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eval_framework.adapters import agent_eval, skill_bench
from eval_framework.metrics import summarize

ROOT = Path(__file__).resolve().parents[2] / 'agent_eval'

def test_suite():
    suite = agent_eval.load_suite(ROOT)
    assert suite.suite_id == 'dsh-skills'
    assert len(suite.cases) > 30
    assert len({case.case_id for case in suite.cases}) == len(suite.cases)
    assert all(len(case.fixture_sha256) == 64 for case in suite.cases)

def test_records():
    records = agent_eval.records(ROOT)
    assert records
    for record in records:
        record.validate()
        assert record.record_hash
        assert summarize(record.attempts)['attempts'] == 1

def test_catalog():
    path = Path(__file__).resolve().parents[2] / 'results' / 'catalog.json'
    data = skill_bench.catalog(path)
    assert 'suites' in data and 'reports' in data

if __name__ == '__main__':
    test_suite(); test_records(); test_catalog(); print('adapters PASS')
