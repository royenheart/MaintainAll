import json, sys
from pathlib import Path
repo=Path(sys.argv[1])
case_id=sys.argv[3] if len(sys.argv)>3 else 'observability-large-trace'
truth=json.loads((Path(__file__).resolve().parents[1]/'truth'/f'{case_id}.json').read_text())
report={}
for name in ('report.json','report.md'):
 p=repo/name
 if p.is_file():
  if name.endswith('.json'):
   try: report=json.loads(p.read_text())
   except Exception: pass
  break
checks={
 'report': bool(report),
 'tool_calls': report.get('tool_calls')==truth.get('tool_calls'),
 'top_tool': report.get('top_tool')==truth.get('tool_by_name',[[None]])[0][0] if truth.get('tool_by_name') else False,
 'tokens': all(report.get(k)==truth.get('tokens',{}).get(k2) for k,k2 in (('input_tokens','inputTokens'),('output_tokens','outputTokens'),('cache_read_tokens','cacheReadTokens'))),
 'p50': report.get('tool_latency_ms_p50')==truth.get('tool_latency_ms_p50'),
 'p95': report.get('tool_latency_ms_p95')==truth.get('tool_latency_ms_p95'),
}
print(json.dumps({'score':sum(checks.values()),'max':len(checks),'checks':checks},ensure_ascii=False,indent=2))
