import json,sys
from pathlib import Path
repo=Path(sys.argv[1]);case='observability-codex-large'
truth=json.loads((Path(__file__).resolve().parents[1]/'truth'/f'{case}.json').read_text())
report={}
p=repo/'report.json'
if p.is_file():
 try: report=json.loads(p.read_text())
 except Exception: pass
items=dict(truth.get('items') or [])
checks={
 'report':bool(report),
 'events':report.get('event_count')==truth.get('event_count'),
 'command':report.get('items_command_execution')==items.get('command_execution'),
 'input':report.get('input_tokens')==truth.get('usage',{}).get('input_tokens'),
 'cached':report.get('cached_input_tokens')==truth.get('usage',{}).get('cached_input_tokens'),
 'output':report.get('output_tokens')==truth.get('usage',{}).get('output_tokens'),
 'cache_rate':report.get('cache_hit_rate')==truth.get('cache_hit_rate'),
 'uncached':report.get('uncached_tokens')==truth.get('uncached_tokens'),
 'compaction':report.get('compaction_events')==truth.get('compaction_events'),
}
print(json.dumps({'score':sum(checks.values()),'max':len(checks),'checks':checks},ensure_ascii=False,indent=2))
