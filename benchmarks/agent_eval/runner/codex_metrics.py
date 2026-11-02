"""Parse Codex CLI `--json` event JSONL into observability fields."""
import json, sys
from collections import Counter
from pathlib import Path

events = []
for line in Path(sys.argv[1]).read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        events.append(json.loads(line))
    except Exception:
        pass

types = Counter(e.get('type') for e in events)
items = Counter((e.get('item') or {}).get('type') for e in events if e.get('type') == 'item.completed')
usage = {}
for e in events:
    if e.get('type') == 'turn.completed':
        usage = e.get('usage') or usage
compaction = [e for e in events if 'compact' in str(e.get('type', '')).lower() or 'compact' in json.dumps(e.get('item') or {}).lower()]
print(json.dumps({
    'event_types': types.most_common(),
    'items': items.most_common(),
    'usage': usage,
    'cache_hit_rate': round((usage.get('cached_input_tokens') or 0) / ((usage.get('input_tokens') or 0) + (usage.get('cached_input_tokens') or 0)), 3) if ((usage.get('input_tokens') or 0) + (usage.get('cached_input_tokens') or 0)) else None,
    'compaction_events': len(compaction),
    'compaction_types': Counter(str(e.get('type')) for e in compaction).most_common(),
    'event_count': len(events),
}, ensure_ascii=False, indent=2))
