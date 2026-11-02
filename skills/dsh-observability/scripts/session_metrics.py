"""Event-derived observability for one dsh trial.

Reads a `result.json` produced by `dsh_task.mjs`; no model calls, no grader logic.
All token/cache fields come from the session's assistant usage records.
"""
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

path = Path(sys.argv[1])
data = json.loads(path.read_text())
events = sorted(data.get('events') or [], key=lambda e: e.get('seq', 0))
calls, results = [], {}
for e in events:
    if e.get('type') == 'tool/call':
        calls.append(e)
    elif e.get('type') == 'tool/result':
        d = e.get('data') or {}
        cid = d.get('toolCallId') or (d.get('message') or {}).get('toolCallId')
        if cid:
            results[cid] = e

def parse_args(raw):
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or '{}')
    except Exception:
        return {}

def target(name, args):
    if not isinstance(args, dict):
        return ''
    for key in ('file_path', 'filePath', 'path', 'target'):
        if isinstance(args.get(key), str) and args[key]:
            return args[key]
    if name in ('bash', 'shell'):
        return ' '.join(str(args.get('command') or '').split())[:300]
    if name in ('grep', 'glob', 'search'):
        return ' '.join(str(args.get(k, '')) for k in ('pattern', 'path', 'glob') if args.get(k))[:300]
    return str(args.get('description') or '')[:200]

def result_text(event):
    if not event:
        return ''
    d = event.get('data') or {}
    msg = d.get('message') or {}
    parts = []
    for c in msg.get('content') or []:
        if isinstance(c, dict) and isinstance(c.get('text'), str):
            parts.append(c['text'])
    return '\n'.join(parts)

def is_error(event):
    if not event:
        return False
    d = event.get('data') or {}
    msg = d.get('message') or {}
    if msg.get('isError'):
        return True
    text = result_text(event)
    return 'requires reading' in text or 'file changed since' in text

tool_rows = []
for e in calls:
    d = e.get('data') or {}
    name = d.get('name') or '?'
    args = parse_args(d.get('arguments'))
    cid = d.get('callId')
    res = results.get(cid)
    latency = (res.get('time') - e.get('time')) if res and isinstance(e.get('time'), (int, float)) and isinstance(res.get('time'), (int, float)) else None
    text = result_text(res)
    tool_rows.append({'name': name, 'target': target(name, args), 'args': args, 'call': e, 'result': res, 'latency_ms': latency, 'error': is_error(res), 'result_chars': len(text)})

names = Counter(r['name'] for r in tool_rows)
errors = Counter(r['name'] for r in tool_rows if r['error'])
read_rows = [r for r in tool_rows if r['name'] == 'read']
write_rows = [r for r in tool_rows if r['name'] in ('write', 'edit', 'apply_patch')]
bash_rows = [r for r in tool_rows if r['name'] == 'bash']
skill_rows = [r for r in tool_rows if r['name'] == 'skill']
ref_rows = [r for r in tool_rows if r['name'] == 'read' and '/references/' in r['target']]
mp_rows = [r for r in tool_rows if r['name'] == 'read' and 'model-policy' in r['target']]
first_edit = next((i for i, r in enumerate(tool_rows) if r['name'] in ('write', 'edit', 'apply_patch')), None)
last_edit = max((i for i, r in enumerate(tool_rows) if r['name'] in ('write', 'edit', 'apply_patch')), default=None)
verify_re = re.compile(r'\b(test|tests|build|typecheck|lint|dump-config|npm pack|install|uninstall|pytest|node --test|verify)\b', re.I)
verify_rows = [r for r in bash_rows if verify_re.search(r['target'])]
call_counter = Counter((r['name'], r['target']) for r in tool_rows)
repeats = [(f'{n}:{t}', c) for (n, t), c in call_counter.items() if c > 1]

usage_keys = ('inputTokens', 'outputTokens', 'cacheReadTokens', 'cacheWriteTokens', 'totalTokens')
usage = {k: 0 for k in usage_keys}
usage_events = 0
assistant = 0
reasoning_chars = 0
assistant_chars = 0
system_prompt_bytes = 0
for e in events:
    if e.get('type') == 'assistant/message':
        assistant += 1
        d = e.get('data') or {}
        u = d.get('usage') or {}
        if u:
            usage_events += 1
            for k in usage_keys:
                usage[k] += int(u.get(k) or 0)
        msg = d.get('message') or {}
        for c in msg.get('content') or []:
            if isinstance(c, dict):
                if c.get('type') == 'reasoning' and isinstance(c.get('text'), str):
                    reasoning_chars += len(c['text'])
                if c.get('type') == 'text' and isinstance(c.get('text'), str):
                    assistant_chars += len(c['text'])
    elif e.get('type') == 'system/message':
        system_prompt_bytes += len(json.dumps((e.get('data') or {}).get('message') or {}, ensure_ascii=False))

context_window = None
tool_schema_bytes = 0
for e in events:
    if e.get('type') == 'request/context':
        context_window = (e.get('data') or {}).get('contextWindow') or context_window
    elif e.get('type') == 'request/header':
        header = (e.get('data') or {}).get('header') or {}
        tool_schema_bytes = len(json.dumps(header.get('tools') or [], ensure_ascii=False))

compaction = [e for e in events if str(e.get('type', '')).startswith('compaction/')]
def summary_chars(value):
    if isinstance(value, list):
        return sum(len(block.get('text') or '') for block in value if isinstance(block, dict))
    return len(value or '') if isinstance(value, str) else 0
compaction_summary_chars = sum(summary_chars((e.get('data') or {}).get('summary')) for e in compaction)
compaction_shadowed = sum(len((e.get('data') or {}).get('shadowedSeqs') or []) for e in compaction)
compaction_starts = sum(1 for e in compaction if e.get('type') == 'compaction/start')
compaction_summaries = sum(1 for e in compaction if e.get('type') == 'compaction/summary')
compaction_prunes = sum(1 for e in compaction if e.get('type') == 'compaction/prune')
compaction_ends = sum(1 for e in compaction if e.get('type') == 'compaction/end')
total_tool_ms = sum(r['latency_ms'] for r in tool_rows if r['latency_ms'] is not None)
times = [e.get('time') for e in events if isinstance(e.get('time'), (int, float))]
wall_ms = (max(times) - min(times)) if len(times) >= 2 else None
model_ms = max(0, wall_ms - total_tool_ms) if wall_ms is not None else None
edit_times = [r['call'].get('time') for r in write_rows if isinstance(r['call'].get('time'), (int, float))]
first_edit_ms = (min(edit_times) - min(times)) if edit_times and times else None
last_edit_ms = (max(edit_times) - min(times)) if edit_times and times else None
phase_after_edit_ms = (max(times) - max(edit_times)) if edit_times and times else None
latencies = sorted(r['latency_ms'] for r in tool_rows if r['latency_ms'] is not None)
def pct(p):
    if not latencies:
        return None
    return latencies[min(len(latencies) - 1, int(len(latencies) * p))]

out = {
    'sessionId': data.get('sessionId'),
    'final_chars': len(data.get('finalResponse') or ''),
    'wall_ms': wall_ms,
    'model_ms_approx': model_ms,
    'tool_ms': total_tool_ms,
    'turns': sum(1 for e in events if e.get('type') == 'turn/start'),
    'steps': sum(1 for e in events if e.get('type') == 'step/start'),
    'assistant_messages': assistant,
    'tool_calls': len(tool_rows),
    'tool_by_name': names.most_common(20),
    'tool_errors': sum(errors.values()),
    'tool_errors_by_name': errors.most_common(10),
    'tool_error_rate': round(sum(errors.values()) / len(tool_rows), 3) if tool_rows else None,
    'tool_latency_ms_p50': pct(0.5),
    'tool_latency_ms_p95': pct(0.95),
    'tool_latency_ms_max': max(latencies) if latencies else None,
    'read_calls': len(read_rows),
    'write_calls': len(write_rows),
    'bash_calls': len(bash_rows),
    'skill_calls': len(skill_rows),
    'skill_names': [r['args'].get('name') for r in skill_rows],
    'model_policy_calls': sum(1 for r in skill_rows if r['args'].get('name') == 'model-policy'),
    'reference_reads': len(ref_rows),
    'reference_files': [Path(r['target']).name for r in ref_rows],
    'reference_bytes': sum(r['result_chars'] for r in ref_rows),
    'model_policy_reads': len(mp_rows),
    'unique_reads': len({r['target'] for r in read_rows}),
    'unique_writes': len({r['target'] for r in write_rows}),
    'read_result_chars': sum(r['result_chars'] for r in read_rows),
    'write_arg_chars': sum(len(json.dumps(r['args'], ensure_ascii=False)) for r in write_rows),
    'calls_before_first_edit': first_edit,
    'calls_after_first_edit': (len(tool_rows) - first_edit) if first_edit is not None else None,
    'first_edit_ms': first_edit_ms,
    'last_edit_ms': last_edit_ms,
    'phase_after_edit_ms': phase_after_edit_ms,
    'verification_calls': len(verify_rows),
    'verification_examples': [r['target'][:180] for r in verify_rows[:5]],
    'repeated_calls': sorted(repeats, key=lambda x: -x[1])[:8],
    'max_repeat': max((c for _, c in repeats), default=0),
    'tokens': usage,
    'uncached_tokens': usage['inputTokens'] + usage['outputTokens'],
    'usage_events': usage_events,
    'cache_hit_rate': round(usage['cacheReadTokens'] / (usage['inputTokens'] + usage['cacheReadTokens'] + usage['cacheWriteTokens']), 3) if (usage['inputTokens'] + usage['cacheReadTokens'] + usage['cacheWriteTokens']) else None,
    'tokens_per_s_model': round(usage['outputTokens'] / (model_ms / 1000), 1) if model_ms and model_ms > 0 else None,
    'context_window': context_window,
    'tool_schema_bytes': tool_schema_bytes,
    'system_prompt_bytes': system_prompt_bytes,
    'reasoning_chars': reasoning_chars,
    'assistant_chars': assistant_chars,
    'compaction_events': compaction_starts or compaction_summaries,
    'compaction_starts': compaction_starts,
    'compaction_summaries': compaction_summaries,
    'compaction_prunes': compaction_prunes,
    'compaction_ends': compaction_ends,
    'compaction_types': Counter(str(e.get('type')) for e in compaction).most_common(),
    'compaction_summary_chars': compaction_summary_chars,
    'compaction_shadowed_events': compaction_shadowed,
}
print(json.dumps(out, ensure_ascii=False, indent=2))
