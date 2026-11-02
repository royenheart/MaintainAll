import json,sys
from pathlib import Path
repo=Path(sys.argv[1]);case=sys.argv[3] if len(sys.argv)>3 else ''
truth=json.loads((Path(__file__).resolve().parents[1]/'truth'/f'{case}.json').read_text())
report={}
p=repo/'report.json'
if p.is_file():
 try: report=json.loads(p.read_text())
 except Exception: pass
top=truth.get('tool_by_name') or [[None,None]]
checks={
 'report':bool(report),
 'tool_calls':report.get('tool_calls')==truth.get('tool_calls'),
 'top_count':report.get('top_tool_count')==top[0][1],
 'p50':report.get('tool_latency_ms_p50')==truth.get('tool_latency_ms_p50'),
 'p95':report.get('tool_latency_ms_p95')==truth.get('tool_latency_ms_p95'),
 'compaction':report.get('compaction_events')==truth.get('compaction_events'),
 'summary':report.get('compaction_summary_chars')==truth.get('compaction_summary_chars'),
}
print(json.dumps({'score':sum(checks.values()),'max':len(checks),'checks':checks},ensure_ascii=False,indent=2))
