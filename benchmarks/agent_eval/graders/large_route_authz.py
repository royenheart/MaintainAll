import json,re,sys
from pathlib import Path
repo=Path(sys.argv[1]);text=(repo/'report.md').read_text() if (repo/'report.md').is_file() else ''
t=text.lower()
checks={
 'report':bool(text.strip()),
 'route_path': '/plugins/maintainall/admin' in text,
 'missing_gate':bool(re.search(r'(requestrejection|host.?gate|auth|鉴权|认证|gate).{0,100}(missing|没有|未|无|absent|not|without|no )',t)) or bool(re.search(r'(没有|未|无|missing|without|no ).{0,80}(requestrejection|host.?gate|auth|鉴权|认证|gate)',t)),
 'file':bool(re.search(r'src/index\.ts',t)),
 'severity':bool(re.search(r'(critical|high|严重|高|p[01])',t)),
 'fix':bool(re.search(r'(fence|gate|requestrejection|鉴权|中间件|middleware).{0,100}(wrap|包裹|添加|add|use|修复|remediation)',t)) or bool(re.search(r'(修复|移除|加固|remediation|remove|fix).{0,80}(route|路由|admin|fence|gate)',t)),
 'evidence':bool(re.search(r'(webServer\.register|register\(|line|行号)',t)),
}
print(json.dumps({'score':sum(checks.values()),'max':len(checks),'checks':checks},ensure_ascii=False,indent=2))
