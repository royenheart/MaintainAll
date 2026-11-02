import json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
events = [
 {'type':'assistant/message','data':{'usage':{'inputTokens':10,'outputTokens':2,'cacheReadTokens':3}}},
 {'type':'compaction/start','data':{}},
 {'type':'compaction/summary','data':{}},
 {'type':'compaction/prune','data':{}},
]
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'session.jsonl'; p.write_text('\n'.join(json.dumps(e) for e in events))
 out=json.loads(subprocess.run([sys.executable,str(ROOT/'scripts/session_events.py'),str(p)],capture_output=True,text=True,check=True).stdout)
assert out['events']==4 and out['compactions']==1 and out['summaries']==1 and out['prunes']==1
assert out['usage']['inputTokens']==10
print('dsh-observability session_events test: PASS')
