import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eval_framework.comparison import summarize
from eval_framework.contracts import Attempt, Record, RunManifest


def rec(case, arm, reward):
    m = RunManifest(run_id=f'{case}-{arm}', suite='dsh-skills', case=case, arm=arm,
                    workflow_sha256='a'*64, prompt_sha256='b'*64, skill_sha256=None,
                    agent_runtime='dsh', model='m', provider='p', source='test',
                    environment={'case_sha256':'c'*64,'grader_sha256':'d'*64,'truth_sha256':'e'*64,
                                 'fixture_sha256':'f'*64,'baseline_skill_sha256':'0'*64},
                    budgets={'max_tool_calls':10})
    return Record(record_id=m.run_id, manifest=m, state='sealed',
                  attempts=(Attempt('a1', 't1', 'scored', reward, 10),), metrics={}).with_hash()

records = [rec('c1','with',8), rec('c1','without',5), rec('c2','with',6), rec('c2','without',5)]
result = summarize(records)
assert result['paired_cases'] == 2 and abs(result['mean_delta'] - 0.2) < 1e-9 and result['verdict'] == 'not-comparable'
print('comparison PASS')
