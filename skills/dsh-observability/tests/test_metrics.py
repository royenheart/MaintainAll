import json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
events = [
 {'type':'turn/start','seq':1,'time':1000,'data':{}},
 {'type':'assistant/message','seq':2,'time':1100,'data':{'usage':{'inputTokens':100,'outputTokens':50,'cacheReadTokens':200,'cacheWriteTokens':50,'totalTokens':400},'message':{'role':'assistant','content':[{'type':'reasoning','text':'r'*20}]}}},
 {'type':'tool/call','seq':3,'time':1200,'data':{'callId':'c1','name':'read','arguments':json.dumps({'file_path':'/work/skills/x/references/a.md'})}},
 {'type':'tool/result','seq':4,'time':1300,'data':{'toolCallId':'c1','message':{'role':'tool','content':[{'type':'text','text':'x'*40}],'isError':False}}},
 {'type':'compaction/start','seq':5,'time':1400,'data':{}},
 {'type':'compaction/summary','seq':6,'time':1450,'data':{'summary':[{'type':'text','text':'s'*100}],'shadowedSeqs':[1,2]}},
 {'type':'compaction/prune','seq':7,'time':1500,'data':{'shadowedSeqs':[3]}},
 {'type':'compaction/end','seq':8,'time':1550,'data':{}},
]
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'result.json'; p.write_text(json.dumps({'sessionId':'t','events':events}))
 out=json.loads(subprocess.run([sys.executable,str(ROOT/'scripts/session_metrics.py'),str(p)],capture_output=True,text=True,check=True).stdout)
assert out['tokens']['totalTokens']==400
assert out['cache_hit_rate']==round(200/350,3)
assert out['reference_reads']==1 and out['reference_bytes']==40
assert out['compaction_events']==1 and out['compaction_summaries']==1 and out['compaction_prunes']==1
assert out['compaction_summary_chars']==100 and out['compaction_shadowed_events']==3
assert out['uncached_tokens']==150
print('dsh-observability metrics test: PASS')
