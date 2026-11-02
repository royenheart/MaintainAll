import json, re, sys
from pathlib import Path
repo = Path(sys.argv[1]).resolve()
text = (repo / 'report.md').read_text() if (repo / 'report.md').is_file() else ''
t = text.lower()
checks = {
    'report': bool(text.strip()),
    'serialize_package': 'serialize-javascript' in t,
    'advisory_id': 'ghsa-76p7-773f-r4q5' in t or 'ghsa-5c6j-r48x-rmvq' in t,
    'cve': 'cve-2024-11831' in t,
    'fixed_version': '6.0.2' in t or '7.0.3' in t,
    'issue_7': bool(re.search(r'(issue|问题|#)\s*#?7\b|issues/7|#7', t)),
    'verdict': bool(re.search(r'(阻止|block|不可安装|do not install|升级|upgrade|需要修复)', t)),
    'no_leftpad_false_positive': not bool(re.search(r'left-pad.{0,100}(vulnerab|cve-|ghsa-)', t)),
}
score = sum(checks.values())
print(json.dumps({'score': score, 'max': len(checks), 'checks': checks}, ensure_ascii=False, indent=2))
sys.exit(0)
