import json, re, sys
from pathlib import Path
repo = Path(sys.argv[1]).resolve()
text = (repo / 'report.md').read_text() if (repo / 'report.md').is_file() else ''
t = text.lower()
ids = ['ghsa-xvch-5gv4-984h','ghsa-29mw-wpgm-hmr9','ghsa-35jh-r3h4-6jhm','ghsa-76p7-773f-r4q5','ghsa-9c47-m6qq-7p4h','ghsa-72xf-g2v4-qvf3']
fixes = ['1.2.6','4.17.21','6.0.2','2.2.2','4.1.3']
cves = ['cve-2021-44906','cve-2020-28500','cve-2021-23337','cve-2024-11831','cve-2022-46175','cve-2023-26136']
checks = {
 'report': bool(text.strip()),
 'all_advisory_ids': all(x in t for x in ids),
 'all_fixed_versions': all(x in t for x in fixes),
 'all_cves': all(x in t for x in cves),
 'issue_101': bool(re.search(r'(issue|问题|#)\s*#?101\b|issues/101|#101', t)),
 'security_issue_context': bool(re.search(r'(issue|问题|#)\s*#?101.{0,200}(security|安全|pollution|cve|ghsa)', t, re.S)) or bool(re.search(r'(security|安全).{0,200}101', t, re.S)),
 'verdict': bool(re.search(r'(阻止|block|不可安装|do not install|升级|upgrade|需要修复)', t)),
 'no_leftpad_fp': not bool(re.search(r'left-pad.{0,100}(vulnerab|cve-|ghsa-|security)', t)),
 'no_is_number_fp': not bool(re.search(r'is-number.{0,100}(vulnerab|cve-|ghsa-|security)', t)),
 'no_unrelated_issue_102': not bool(re.search(r'(issue|#)\s*#?102.{0,60}(cve-|ghsa-|is a security|是安全漏洞)', t, re.S)),
 'no_unrelated_issue_103': not bool(re.search(r'(issue|#)\s*#?103.{0,60}(cve-|ghsa-|is a security|是安全漏洞)', t, re.S)),
}
score = sum(checks.values())
print(json.dumps({'score': score, 'max': len(checks), 'checks': checks}, ensure_ascii=False, indent=2))
sys.exit(0)
