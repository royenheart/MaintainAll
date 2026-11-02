import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eval_framework.contracts import Attempt, Record, RunManifest
from eval_framework.report import build_site
from eval_framework.store import FileRecordStore, StoreError


def record():
    m = RunManifest(run_id='r1', suite='dsh-skills', case='<script>x</script>', arm='with',
                    workflow_sha256='a' * 64, prompt_sha256='b' * 64, skill_sha256=None,
                    agent_runtime='dsh', model='m', provider='p', source='test')
    return Record(record_id='r1', manifest=m, state='sealed',
                  attempts=(Attempt('a1', 't1', 'scored', 2, 2),), metrics={}).with_hash()


def test_store():
    with tempfile.TemporaryDirectory() as td:
        store = FileRecordStore(Path(td))
        store.seal(record())
        assert len(store.list()) == 1
        try:
            store.seal(record())
        except StoreError:
            pass
        else:
            raise AssertionError('expected duplicate seal to fail')


def test_report_escapes():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / 'site'
        build_site([record()], [], out, None)
        html = (out / 'index.html').read_text()
        assert '<script>x</script>' not in html
        assert '&lt;script&gt;' in html


if __name__ == '__main__':
    test_store(); test_report_escapes(); print('store/report PASS')
