#!/usr/bin/env python3
"""Summarize a dsh session .zstd log without printing prompts or credentials."""
import json, subprocess, sys
from collections import Counter
from pathlib import Path

path = Path(sys.argv[1])
if path.suffix == '.zstd':
    try:
        raw = subprocess.run(['zstd', '-dc', str(path)], capture_output=True, check=True)
        text = raw.stdout.decode('utf-8', 'replace')
    except FileNotFoundError:
        raise SystemExit('zstd is required to read .zstd sessions; use a plain .jsonl or install zstd')
else:
    text = path.read_text(errors='replace')
events = []
for line in text.splitlines():
    try:
        events.append(json.loads(line))
    except Exception:
        pass
types = Counter(event.get('type') for event in events)
tools = Counter()
usage = Counter()
compaction_counts = Counter()
for event in events:
    data = event.get('data') or {}
    if event.get('type') == 'tool/call':
        tools[data.get('name') or '?'] += 1
    if event.get('type') == 'assistant/message':
        for key, value in (data.get('usage') or {}).items():
            usage[key] += int(value or 0)
    if str(event.get('type', '')).startswith('compaction/'):
        compaction_counts[str(event.get('type'))] += 1
print(json.dumps({
    'session': path.name,
    'events': len(events),
    'event_types': types.most_common(),
    'tool_calls': tools.most_common(),
    'usage': dict(usage),
    'compaction': compaction_counts.most_common(),
    'compactions': compaction_counts.get('compaction/start', 0) or compaction_counts.get('compaction/summary', 0),
    'summaries': compaction_counts.get('compaction/summary', 0),
    'prunes': compaction_counts.get('compaction/prune', 0),
}, ensure_ascii=False, indent=2))
