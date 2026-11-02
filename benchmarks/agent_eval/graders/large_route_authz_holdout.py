import json,re,sys
from pathlib import Path
repo=Path(sys.argv[1]);text=(repo/'report.md').read_text() if (repo/'report.md').is_file() else ''
t=text.lower()
checks={
 'report':bool(text.strip()),
 'route': '/plugins/skills-manager/admin' in text,
 'gate':bool(re.search(r'(requestrejection|host.?gate|auth|鉴权|gate).{0,100}(missing|没有|未|无|without|no )',t)) or bool(re.search(r'(没有|未|无|missing|without).{0,80}(requestrejection|host.?gate|auth|鉴权|gate)',t)),
 'file':bool(re.search(r'security-audit-fixture\.ts|src/',t)),
 'severity':bool(re.search(r'(critical|high|严重|高|p[01])',t)),
 'fix':bool(re.search(r'(fence|gate|requestrejection|修复|移除|remove|fix).{0,100}(route|路由|admin|fence|gate)',t)),
 'evidence':bool(re.search(r'(webserver\.register|register\(|line|行号)',t)),
}
print(json.dumps({'score':sum(checks.values()),'max':len(checks),'checks':checks},ensure_ascii=False,indent=2))
