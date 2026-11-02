import json, sys
from pathlib import Path
repo = Path(sys.argv[1]).resolve()
case_id = sys.argv[3] if len(sys.argv) > 3 else ''
truth_path = Path(__file__).resolve().parents[1] / 'truth' / f'{case_id}.json'
truth = json.loads(truth_path.read_text())
report_path = repo / truth.get('report', 'report.json')
checks = {'report_json': False}
findings = []
try:
    data = json.loads(report_path.read_text())
    checks['report_json'] = isinstance(data, dict)
    checks['report_verdict'] = data.get('verdict') in truth.get('verdicts', [])
    checks['not_verified'] = isinstance(data.get('notVerified'), list) and all(isinstance(x, str) for x in data['notVerified']) and bool(data['notVerified'])
    findings = data.get('findings') if isinstance(data.get('findings'), list) else []
except Exception:
    data = {}
    checks['report_verdict'] = False
    checks['not_verified'] = False
def norm(text): return str(text or '').replace('\\', '/').lower()
def valid(f):
    return (isinstance(f, dict) and isinstance(f.get('file'), str) and isinstance(f.get('line'), int)
            and f.get('severity') in ('critical','high','medium','review','low')
            and isinstance(f.get('evidence'), str) and isinstance(f.get('why'), str))
checks['schema'] = bool(findings) and all(valid(f) for f in findings)
used = set()
for expected in truth.get('findings', []):
    matched = False
    for index, got in enumerate(findings):
        if index in used or not valid(got):
            continue
        file_ok = norm(got['file']).endswith(norm(expected['file']))
        line_ok = got['line'] in (expected.get('lines') or [int(expected.get('line', 0))])
        severity_ok = got['severity'] in (expected.get('severities') or [expected.get('severity')]) or (expected.get('severity') == 'high' and got['severity'] == 'critical')
        blob = norm(got['evidence']) + ' ' + norm(got['why'])
        terms_ok = all(norm(term) in blob for term in (expected.get('must_mention') or []))
        evidence_ok = all(norm(term) in norm(got.get('evidence')) for term in (expected.get('evidence_terms') or []))
        if file_ok and line_ok and severity_ok and terms_ok and evidence_ok:
            matched = True; used.add(index); break
    checks['finding:'+expected['id']] = matched
extra = [f for i,f in enumerate(findings) if i not in used and valid(f) and f.get('severity') in ('high','critical')]
checks['no_unsupported_findings'] = bool(truth.get('allow_extra_high')) or not extra
score = sum(checks.values())
print(json.dumps({'score': score, 'max': len(checks), 'checks': checks, 'extra': extra[:3]}, ensure_ascii=False, indent=2))
sys.exit(0)
