import json, re, sys
from pathlib import Path
repo = Path(sys.argv[1]).resolve()
text = (repo / 'report.md').read_text() if (repo / 'report.md').is_file() else ''
t = text.lower()
result = repo.parent / 'result.json'
if not result.is_file():
    result = repo / 'result.json'
events = []
if result.is_file():
    try:
        events = json.loads(result.read_text()).get('events') or []
    except Exception:
        events = []
subagents = []
for event in events:
    if event.get('type') != 'tool/call':
        continue
    data = event.get('data') or {}
    name = str(data.get('name') or '')
    if 'subagent' not in name.lower() and name != 'task':
        continue
    raw = data.get('arguments')
    try:
        args = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        args = {}
    subagents.append({'name': name, 'args': args})
def read_only(args):
    blob = json.dumps(args, ensure_ascii=False).lower()
    return any(word in blob for word in ('read-only', 'readonly', '只读', 'do not edit', 'no edit', '不要修改'))
checks = {
    'report': bool(text.strip()),
    'subagent_count': 3 <= len(subagents) <= 4,
    'subagent_read_only': bool(subagents) and all(read_only(item['args']) for item in subagents),
    'token_source': bool(re.search(r'(lib/telemetry\.js|telemetry\.js).{0,80}(DSH_TOKEN|token)|(DSH_TOKEN|token).{0,80}lib/telemetry\.js', t, re.S)),
    'network_sink': bool(re.search(r'(client/sync\.js|sync\.js).{0,80}collector\.example\.invalid|collector\.example\.invalid.{0,80}(client/sync\.js|sync\.js)', t, re.S)),
    'cross_surface': bool(re.search(r'(DSH_TOKEN|token).{0,200}(collector\.example\.invalid|sync\.js|外传|exfiltr)', t, re.S)) and bool(re.search(r'(跨|cross|join|merge|链路)', t)),
    'host_route': bool(re.search(r'(lib/host\.js|host\.js).{0,100}(webServer|register|route|路由)|(webServer|register|route|路由).{0,100}(lib/host\.js|host\.js)', t, re.S)),
    'install_script': bool(re.search(r'postinstall|安装脚本|install\.js', t)),
    'client_html': bool(re.search(r'(innerhtml|html 注入|html injection).{0,100}panel\.js|panel\.js.{0,100}(innerhtml|html)', t, re.S)),
    'issue_203': bool(re.search(r'(issue|问题|#)\s*#?203\b|issues/203|#203', t)),
    'verdict': bool(re.search(r'(阻止|block|不可安装|do not install)', t)),
}
keys = list(checks); score = sum(checks.values())
print(json.dumps({'score': score, 'max': len(keys), 'checks': checks, 'subagents': [s['name'] for s in subagents]}, ensure_ascii=False, indent=2))
sys.exit(0)
