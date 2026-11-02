import json, re, sys
from pathlib import Path
repo = Path(sys.argv[1]).resolve()
text = (repo / 'report.md').read_text() if (repo / 'report.md').is_file() else ''
t = text.lower()
checks = {
    'report': bool(text.strip()),
    'minimist_id': 'ghsa-xvch-5gv4-984h' in t,
    'minimist_cve': 'cve-2021-44906' in t,
    'minimist_fixed': '1.2.6' in t,
    'lodash_advisory': 'ghsa-29mw-wpgm-hmr9' in t or 'ghsa-35jh-r3h4-6jhm' in t,
    'lodash_fixed': '4.17.21' in t,
    'issue_42': bool(re.search(r'(issue|问题|#)\s*#?42\b|issues/42|#42', t)),
    'verdict': bool(re.search(r'(阻止|block|不可安装|do not install|升级|upgrade|需要修复)', t)),
    'no_leftpad_false_positive': not bool(re.search(r'left-pad.{0,100}(vulnerab|cve-|ghsa-)', t)),
}
keys = list(checks); score = sum(checks.values())
print(json.dumps({'score': score, 'max': len(keys), 'checks': checks}, ensure_ascii=False, indent=2))
sys.exit(0)
