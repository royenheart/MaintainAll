import json, sys
from pathlib import Path
root = Path(__file__).resolve().parents[3]
fixture = root / 'benchmarks/agent_eval/fixtures/session-d26-sandbox.json'
data = json.loads(fixture.read_text())
obs = data['observations']
assert obs[0]['classification'] == 'sandbox-boundary'
assert obs[1]['classification'] == 'host-capability'
assert obs[2]['classification'] == 'sandbox-boundary'
assert data['expected_decision'] == 'widen-mode-or-host-runner'
blob = json.dumps(data, ensure_ascii=False).lower()
for forbidden in ('/home/', 'sk-lf-', 'pk-lf-'):
    assert forbidden not in blob
claims = json.dumps([item.get('claim', '') for item in obs]).lower()
for conclusion in data['forbidden_conclusions']:
    assert conclusion not in claims
# A replay decision must not turn a confined device/process failure into a host fact.
def classify(item):
    if item.get('classification') == 'host-capability':
        return 'host'
    return 'sandbox'
assert [classify(item) for item in obs] == ['sandbox', 'host', 'sandbox']

# Real isolation contrast: the default bwrap view must not expose GPU devices.
import tempfile
sys.path.insert(0, str(root / 'benchmarks/agent_eval/runner'))
import isolate
with tempfile.TemporaryDirectory() as td:
    result = isolate.run(Path(td), False, 'set -eu; test ! -e /dev/nvidia0; test ! -e /dev/nvidiactl; test ! -e /dev/dri/renderD128; echo sandbox-ok')
    assert 'sandbox-ok' in result.stdout, result.stderr
print('dsh-runtime-guide sandbox fixture/isolation test: PASS')
