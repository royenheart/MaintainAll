import json, re, sys
from pathlib import Path
repo=Path(sys.argv[1]).resolve(); text=(repo/'report.md').read_text() if (repo/'report.md').is_file() else ''
t=text.lower()
checks={
 'report': bool(text.strip()),
 'hidden_route': bool(re.search(r'hidden\.js.{0,100}(cap/collect|register|route|路由)|(cap/collect|hidden\.js).{0,100}(register|route|路由)', t, re.S)),
 'hidden_route_severity': bool(re.search(r'(high|高|严重).{0,100}hidden\.js|hidden\.js.{0,100}(high|高|严重)', t, re.S)),
 'patch_disabled': bool(re.search(r'(auth-gate|auth gate).{0,100}(disabled|禁用|关闭)|disabled.{0,100}auth-gate', t, re.S)),
 'issue_301': bool(re.search(r'(issue|#)\s*#?301\b|#301', t)),
 'no_guarded_route_high': not bool(re.search(r'(finding|severity).{0,50}(high|critical).{0,100}(host\.js|cap/safe)|(host\.js|cap/safe).{0,50}(high|critical).{0,50}(finding|severity)', t, re.S)),
 'no_env_high': not bool(re.search(r'(finding|severity).{0,50}(high|critical).{0,100}(telemetry\.js|DSH_TOKEN)|(telemetry\.js|DSH_TOKEN).{0,50}(high|critical).{0,50}(finding|severity)', t, re.S)),
 'not_verified': bool(re.search(r'(not verified|未验证|not checked)', t)),
 'verdict': bool(re.search(r'(block|阻止|不可安装|review|review)', t)),
}
score=sum(checks.values()); print(json.dumps({'score':score,'max':len(checks),'checks':checks},ensure_ascii=False,indent=2)); sys.exit(0)
