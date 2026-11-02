import json, re, sys
from pathlib import Path
repo=Path(sys.argv[1]).resolve(); text=(repo/'report.md').read_text() if (repo/'report.md').is_file() else ''
t=text.lower()
checks={
 'report': bool(text.strip()),
 'clean_verdict': bool(re.search(r'(clean|可以安装|safe to install|allow)', t)) and not bool(re.search(r'(block|阻止|不可安装|do not install)', t)),
 'minimist_fixed': bool(re.search(r'minimist.{0,80}1\.2\.6|1\.2\.6.{0,80}minimist', t)),
 'eventstream_not_installed': bool(re.search(r'(json5|event-stream).{0,100}(not installed|未安装|不在|not in lockfile)', t)),
 'no_real_finding': not bool(re.search(r'(finding|漏洞|vulnerab).{0,80}(ghsa-|cve-)', t)),
 'issue_56_not_blocker': not bool(re.search(r'(issue|#)\s*#?56.{0,60}(cve-|ghsa-|is a security issue)', t)),
 'not_verified': bool(re.search(r'(not verified|未验证|not checked|live osv|没有验证)', t)),
}
score=sum(checks.values()); print(json.dumps({'score':score,'max':len(checks),'checks':checks},ensure_ascii=False,indent=2)); sys.exit(0)
