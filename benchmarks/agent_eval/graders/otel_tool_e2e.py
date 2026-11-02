import json, sys
from pathlib import Path
repo=Path(sys.argv[1]).resolve(); run=repo.parent
report=(repo/'report.md').read_text() if (repo/'report.md').is_file() else ''
events=[]
rp=run/'result.json'
if rp.is_file():
    try: events=json.loads(rp.read_text()).get('events') or []
    except Exception: events=[]
calls=[]
for e in events:
    if e.get('type')!='tool/call': continue
    d=e.get('data') or {}
    if d.get('name')=='otel_echo': calls.append(d.get('arguments'))
checks={
 'report': bool(report.strip()),
 'report_has_hello': 'hello from dsh' in report,
 'tool_called': bool(calls),
 'call_args_text': any('hello from dsh' in str(c) for c in calls),
}
print(json.dumps({'score':sum(checks.values()),'max':len(checks),'checks':checks},ensure_ascii=False,indent=2));sys.exit(0)
