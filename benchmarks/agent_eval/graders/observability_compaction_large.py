import json,sys
from pathlib import Path
repo=Path(sys.argv[1]);case='observability-compaction-large'
truth=json.loads((Path(__file__).resolve().parents[1]/'truth'/f'{case}.json').read_text())
report={}
p=repo/'report.json'
if p.is_file():
 try: report=json.loads(p.read_text())
 except Exception: pass
checks={
 'report':bool(report),
 'tool_calls':report.get('tool_calls')==truth.get('tool_calls'),
 'p50':report.get('tool_latency_ms_p50')==truth.get('tool_latency_ms_p50'),
 'p95':report.get('tool_latency_ms_p95')==truth.get('tool_latency_ms_p95'),
 'compaction_events':report.get('compaction_events')==truth.get('compaction_events'),
 'summary_chars':report.get('compaction_summary_chars')==truth.get('compaction_summary_chars'),
 'shadowed':report.get('compaction_shadowed_events')==truth.get('compaction_shadowed_events'),
 'top_count':report.get('top_tool_count')==truth.get('tool_by_name',[[None,None]])[0][1],
}
print(json.dumps({'score':sum(checks.values()),'max':len(checks),'checks':checks},ensure_ascii=False,indent=2))
