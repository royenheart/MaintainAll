#!/usr/bin/env python3
"""Export a dsh result/session as OTLP/HTTP JSON traces without raw prompts.

Input: result.json from the SDK, or a plain/zstd session JSONL.
Output: OTLP JSON envelope on stdout or --out, optionally POST to an OTLP endpoint.
Only derived fields (counts, hashes, timings, token counters) are emitted.
"""
import argparse, base64, hashlib, json, os, subprocess, sys, urllib.request
from urllib.request import HTTPRedirectHandler, HTTPSHandler, build_opener
import ssl
from pathlib import Path

def load_events(path):
    if path.suffix == '.zstd':
        raw = subprocess.run(['zstd', '-dc', str(path)], capture_output=True, check=True)
        text = raw.stdout.decode('utf-8', 'replace')
    else:
        text = path.read_text(errors='replace')
    if path.suffix == '.json' or path.name == 'result.json':
        data = json.loads(text)
        return data.get('sessionId') or path.stem, data.get('events') or [], data
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            pass
    return path.stem, events, {'events': events}

def h(text, n=16):
    return hashlib.sha256(str(text).encode()).hexdigest()[:n]

def attr(key, value):
    if isinstance(value, bool):
        return {'key': key, 'value': {'boolValue': value}}
    if isinstance(value, int):
        return {'key': key, 'value': {'intValue': str(value)}}
    if isinstance(value, float):
        return {'key': key, 'value': {'doubleValue': value}}
    return {'key': key, 'value': {'stringValue': str(value)}}

def span(trace, sid, name, start, end, attrs, parent=None, status=1):
    return {
        'traceId': trace,
        'spanId': sid,
        'parentSpanId': parent or '',
        'name': name,
        'kind': 1,
        'startTimeUnixNano': str(int(start * 1_000_000)),
        'endTimeUnixNano': str(int(max(start, end) * 1_000_000)),
        'attributes': [attr(k, v) for k, v in attrs.items() if v is not None],
        'status': {'code': status},
    }

def build(session_id, events, data):
    events = sorted(events, key=lambda e: e.get('seq', 0))
    times = [e.get('time') for e in events if isinstance(e.get('time'), (int, float))]
    start = min(times) if times else 0
    end = max(times) if times else start
    trace = h('trace:' + str(session_id), 32)
    root_id = h('root:' + str(session_id), 16)
    model = None
    for e in events:
        if e.get('type') == 'request/context':
            d = e.get('data') or {}
            model = d.get('model') or model
    spans = [span(trace, root_id, 'dsh.run', start, end, {
        'session.id': str(session_id),
        'dsh.model': model,
        'dsh.event_count': len(events),
        'dsh.arm': os.environ.get('AB_MODE'),
    })]
    results = {}
    for e in events:
        if e.get('type') != 'tool/result':
            continue
        d = e.get('data') or {}
        cid = d.get('toolCallId') or (d.get('message') or {}).get('toolCallId')
        if cid:
            results[cid] = e
    assistant = 0
    tool = 0
    compaction = 0
    for e in events:
        typ = e.get('type')
        t = e.get('time') if isinstance(e.get('time'), (int, float)) else start
        d = e.get('data') or {}
        if typ == 'assistant/message':
            assistant += 1
            u = d.get('usage') or {}
            spans.append(span(trace, h(f'a:{assistant}:{t}', 16), 'gen_ai.chat', t, t, {
                'gen_ai.operation.name': 'chat',
                'gen_ai.request.model': model,
                'gen_ai.usage.input_tokens': int(u.get('inputTokens') or 0) + int(u.get('cacheReadTokens') or 0) + int(u.get('cacheWriteTokens') or 0),
                'dsh.usage.uncached_input_tokens': int(u.get('inputTokens') or 0),
                'gen_ai.usage.output_tokens': int(u.get('outputTokens') or 0),
                'gen_ai.usage.cache_read_tokens': int(u.get('cacheReadTokens') or 0),
                'gen_ai.usage.cache_write_tokens': int(u.get('cacheWriteTokens') or 0),
                'dsh.assistant_index': assistant,
            }, root_id))
        elif typ == 'tool/call':
            tool += 1
            name = str(d.get('name') or '?')
            args = d.get('arguments')
            try:
                args = json.loads(args) if isinstance(args, str) else (args or {})
            except Exception:
                args = {}
            target = ''
            for key in ('file_path', 'filePath', 'path', 'target'):
                if isinstance(args.get(key), str):
                    target = args[key]; break
            cid = d.get('callId')
            res = results.get(cid)
            end_t = res.get('time') if res and isinstance(res.get('time'), (int, float)) else t
            result_text = ''
            if res:
                msg = (res.get('data') or {}).get('message') or {}
                result_text = '\n'.join(c.get('text') or '' for c in (msg.get('content') or []) if isinstance(c, dict))
            spans.append(span(trace, h(f't:{tool}:{cid}', 16), 'tool.call', t, end_t, {
                'tool.name': name,
                'tool.call_id': str(cid or ''),
                'tool.target_hash': h(target, 16) if target else None,
                'tool.result_chars': len(result_text),
                'tool.duration_ms': (end_t - t) if end_t >= t else None,
                'tool.is_error': bool(((res or {}).get('data') or {}).get('message', {}).get('isError')),
            }, root_id))
        elif str(typ or '').startswith('compaction/'):
            compaction += 1
            summary = d.get('summary')
            if isinstance(summary, list):
                summary_chars = sum(len(b.get('text') or '') for b in summary if isinstance(b, dict))
            else:
                summary_chars = len(summary or '') if isinstance(summary, str) else 0
            spans.append(span(trace, h(f'c:{compaction}:{t}', 16), 'dsh.compaction', t, t, {
                'dsh.compaction.type': str(typ),
                'dsh.compaction.summary_chars': summary_chars,
                'dsh.compaction.shadowed_events': len(d.get('shadowedSeqs') or []),
            }, root_id))
    return {
        'resourceSpans': [{
            'resource': {'attributes': [attr('service.name', 'dsh'), attr('service.version', 'observability-skill')]},
            'scopeSpans': [{'scope': {'name': 'dsh-observability', 'version': '1'}, 'spans': spans}],
        }]
    }

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('input', type=Path)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--endpoint', default=os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT'))
    ap.add_argument('--offline', action='store_true', help='ignore endpoint/header environment and write JSON only')
    ap.add_argument('--insecure', action='store_true', help='skip TLS verification for a self-signed Langfuse/collector')
    ap.add_argument('--header', action='append', default=[])
    args = ap.parse_args(argv)
    session_id, events, data = load_events(args.input)
    payload = build(session_id, events, data)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + '\n')
    else:
        print(text)
    if args.endpoint and not args.offline:
        endpoint = args.endpoint.rstrip('/')
        if not endpoint.endswith('/v1/traces'):
            endpoint += '/v1/traces'
        headers = {'content-type': 'application/json'}
        raw = os.environ.get('OTEL_EXPORTER_OTLP_HEADERS', '')
        for part in [*args.header, *raw.split(',')]:
            if '=' in part:
                k, v = part.split('=', 1); headers[k.strip()] = v.strip()
        req = urllib.request.Request(endpoint, data=text.encode(), headers=headers, method='POST')
        try:
            handlers = [NoRedirect()]
            if args.insecure:
                handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
            with build_opener(*handlers).open(req, timeout=15) as resp:
                body = resp.read()
                print(f'exported: HTTP {resp.status}', file=sys.stderr)
                try:
                    partial = (json.loads(body or b'{}').get('partialSuccess') or {})
                except Exception:
                    partial = {}
                rejected = int(partial.get('rejectedSpans') or 0)
                if rejected:
                    print(f'error: OTLP rejected {rejected} spans: {partial.get("errorMessage", "")}', file=sys.stderr)
                    return 1
        except Exception as error:
            print(f'error: OTLP export failed: {error}', file=sys.stderr)
            return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
