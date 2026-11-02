import json, sys
from pathlib import Path
repo = Path(sys.argv[1]).resolve()
case_id = sys.argv[3] if len(sys.argv) > 3 else ''
expected_path = Path(__file__).resolve().parents[1] / 'expected' / f'{case_id}.json'
try:
    expected = json.loads(expected_path.read_text())
except Exception as error:
    print(json.dumps({'score': 0, 'max': None, 'error': f'missing expected file: {error}'}))
    sys.exit(0)
report_name = expected.get('report', 'report.md')
report = (repo / report_name).read_text() if (repo / report_name).is_file() else ''
t = report.lower()
import re
checks = {'report': bool(report.strip())}
checks['evidence'] = bool(re.search(r'[A-Za-z0-9_.-]+\.(js|mjs|cjs|ts|tsx|json|yml|yaml):\d+', report, re.I))
for literal in expected.get('must_include', []):
    checks[f'include:{literal}'] = literal.lower() in t
for group in expected.get('must_include_any', []):
    checks['include_any:'+ '|'.join(group)] = any(str(item).lower() in t for item in group)
for literal in expected.get('must_exclude', []):
    checks[f'exclude:{literal}'] = literal.lower() not in t
score = sum(checks.values())
print(json.dumps({'score': score, 'max': len(checks), 'checks': checks}, ensure_ascii=False, indent=2))
sys.exit(0)
