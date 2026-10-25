"""Bounded CLI event classification without exporting messages, paths or IDs."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

MAX_STREAM_BYTES = 8 * 1024 * 1024
MAX_EVENTS = 50000
MAX_EVENT_BYTES = 1024 * 1024
FAILURE_SCOPE = 'failed-turn-v1'
_SHA = re.compile(r'^[0-9a-f]{64}$')
_EVENTS = {'thread.started', 'turn.started', 'turn.completed', 'turn.failed', 'item.started', 'item.updated', 'item.completed', 'error'}
_ITEMS = {'agent_message', 'reasoning', 'command_execution', 'mcp_tool_call', 'file_change', 'web_search', 'todo_list', 'error'}
_FAILURES = {'connection', 'route-discovery', 'timeout', 'rate-limit', 'authorization', 'service-unavailable'}
_INTEGRITY = {'valid', 'missing', 'malformed', 'oversized', 'hash-mismatch', 'event-limit', 'unsafe-file', 'unreadable', 'unsupported-backend'}


def _unknown(integrity):
    return {'schema_version': 1, 'classifier': 'codex-jsonl-v1', 'stream_integrity': integrity, 'model_output': 'unknown', 'event_count': 0, 'model_output_event_count': 0, 'failure_codes': []}


def _codes(message):
    if not isinstance(message, str):
        return set()
    message = message.lower()
    result = set()
    if re.search(r'\bdiscovery\b', message):
        result.add('route-discovery')
    if re.search(r'\b(?:connection|connect|connecting|reconnecting)\b', message):
        result.add('connection')
    if re.search(r'\b(?:timeout|timed out)\b', message):
        result.add('timeout')
    if re.search(r'\b(?:rate limit|429)\b', message):
        result.add('rate-limit')
    if re.search(r'\b(?:unauthorized|forbidden|401|403)\b', message):
        result.add('authorization')
    if re.search(r'\b(?:service unavailable|502|503)\b', message):
        result.add('service-unavailable')
    return result


def _model_item(item):
    kind = item.get('type')
    if kind in {'agent_message', 'reasoning'}:
        return isinstance(item.get('text'), str) and bool(item['text'].strip())
    if kind == 'command_execution':
        return isinstance(item.get('command'), str) and bool(item['command'].strip())
    if kind == 'mcp_tool_call':
        return isinstance(item.get('tool'), str) and bool(item['tool'])
    if kind in {'file_change', 'todo_list'}:
        return isinstance(item.get('changes' if kind == 'file_change' else 'items'), list) and bool(item.get('changes' if kind == 'file_change' else 'items'))
    if kind == 'web_search':
        return bool(item.get('query') or item.get('action'))
    return False


def _supported_item(item):
    """Recognize payload shapes before using an item to establish absence."""
    kind = item.get('type')
    if kind in {'agent_message', 'reasoning', 'error'}:
        return isinstance(item.get('message' if kind == 'error' else 'text'), str)
    if kind == 'command_execution':
        return isinstance(item.get('command'), str)
    if kind == 'mcp_tool_call':
        return isinstance(item.get('tool'), str)
    if kind == 'file_change':
        return isinstance(item.get('changes'), list) and all(isinstance(change, dict) and isinstance(change.get('path'), str) and change.get('kind') in {'add', 'update', 'delete'} for change in item['changes'])
    if kind == 'todo_list':
        return isinstance(item.get('items'), list) and all(isinstance(task, dict) and isinstance(task.get('text'), str) and type(task.get('completed')) is bool for task in item['items'])
    if kind == 'web_search':
        if 'query' in item:
            return isinstance(item['query'], str)
        action = item.get('action')
        if not isinstance(action, dict):
            return False
        if action.get('type') == 'search':
            return isinstance(action.get('query'), str) or isinstance(action.get('queries'), list) and all(isinstance(query, str) for query in action['queries'])
        if action.get('type') == 'open_page':
            return isinstance(action.get('url'), str)
        if action.get('type') == 'find_in_page':
            return isinstance(action.get('url'), str) and isinstance(action.get('pattern'), str)
    return False


def classify_cli_stream(path, *, expected_sha256=None, max_bytes=MAX_STREAM_BYTES):
    """Read one closed ordinary JSONL stream and return an allowlisted summary.

    Missing, malformed, excessive, mismatched or unfamiliar streams never prove
    absence. A valid supported stream can prove that no model-output event was
    observed; it does not prove why the model or transport failed.
    """
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_STREAM_BYTES:
        raise ValueError('CLI stream byte limit must be between one byte and 8 MiB')
    if expected_sha256 is not None and (not isinstance(expected_sha256, str) or not _SHA.fullmatch(expected_sha256)):
        raise ValueError('CLI stream expected hash must be a full SHA-256')
    path = Path(path).absolute()
    try:
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            return _unknown('unsafe-file')
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            return _unknown('unsafe-file')
        if info.st_size > max_bytes:
            return _unknown('oversized')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                return _unknown('unsafe-file')
            data = source.read(max_bytes + 1)
        if len(data) > max_bytes:
            return _unknown('oversized')
    except FileNotFoundError:
        return _unknown('missing')
    except OSError:
        return _unknown('unreadable')
    value = _unknown('valid')
    value.update(stream_sha256=hashlib.sha256(data).hexdigest(), stream_size=len(data))
    if expected_sha256 is not None and value['stream_sha256'] != expected_sha256:
        value['stream_integrity'] = 'hash-mismatch'
        return value
    codes, unknown_schema = set(), False
    lines = data.splitlines()
    if len(lines) > MAX_EVENTS:
        value['stream_integrity'] = 'event-limit'
        return value
    try:
        for line in lines:
            if not line.strip() or len(line) > MAX_EVENT_BYTES:
                raise ValueError('Unsupported CLI event framing')
            event = json.loads(line)
            if not isinstance(event, dict) or not isinstance(event.get('type'), str):
                raise ValueError('Unsupported CLI event shape')
            value['event_count'] += 1
            kind = event['type']
            unknown_schema |= kind not in _EVENTS
            item = event.get('item')
            if kind in {'item.started', 'item.updated', 'item.completed'}:
                if not isinstance(item, dict) or item.get('type') not in _ITEMS or not _supported_item(item):
                    unknown_schema = True
                elif _model_item(item):
                    value['model_output_event_count'] += 1
            objects = [event, event.get('error', {})]
            if isinstance(item, dict) and item.get('type') == 'error':
                objects.append(item)
            for obj in objects:
                if isinstance(obj, dict):
                    codes.update(_codes(obj.get('message')))
    except (ValueError, UnicodeError, RecursionError):
        value['stream_integrity'] = 'malformed'
        # A broken or truncated log cannot establish complete-turn absence.
        value['model_output'] = 'observed' if value['model_output_event_count'] else 'unknown'
        value['failure_codes'] = sorted(codes)
        return value
    value['failure_codes'] = sorted(codes)
    value['model_output'] = 'observed' if value['model_output_event_count'] else 'unknown' if unknown_schema or not lines else 'absent'
    return value


def turn_evidence_scope(status, evidence):
    """Project only checked classification fields into a new evidence scope."""
    valid = isinstance(evidence, dict) and evidence.get('schema_version') == 1 and evidence.get('classifier') == 'codex-jsonl-v1' and evidence.get('stream_integrity') == 'valid' and isinstance(evidence.get('stream_sha256'), str) and bool(_SHA.fullmatch(evidence['stream_sha256'])) and type(evidence.get('stream_size')) is int and 0 < evidence['stream_size'] <= MAX_STREAM_BYTES and type(evidence.get('event_count')) is int and 0 < evidence['event_count'] <= MAX_EVENTS and type(evidence.get('model_output_event_count')) is int and 0 <= evidence['model_output_event_count'] <= evidence['event_count']
    checked = _unknown('unreadable')
    if isinstance(evidence, dict):
        if evidence.get('stream_integrity') in _INTEGRITY:
            checked['stream_integrity'] = evidence['stream_integrity']
        if evidence.get('model_output') in {'observed', 'absent', 'unknown'}:
            checked['model_output'] = evidence['model_output']
        for key, ceiling in (('stream_size', MAX_STREAM_BYTES), ('event_count', MAX_EVENTS), ('model_output_event_count', MAX_EVENTS)):
            if type(evidence.get(key)) is int and 0 <= evidence[key] <= ceiling:
                checked[key] = evidence[key]
        if isinstance(evidence.get('stream_sha256'), str) and _SHA.fullmatch(evidence['stream_sha256']):
            checked['stream_sha256'] = evidence['stream_sha256']
    checked['failure_codes'] = sorted(set(evidence.get('failure_codes', [])) & _FAILURES) if isinstance(evidence, dict) and isinstance(evidence.get('failure_codes'), list) and all(isinstance(code, str) for code in evidence['failure_codes']) else []
    failed = status in {'failed', 'interrupted'}
    absent = failed and valid and evidence.get('model_output') == 'absent' and evidence.get('model_output_event_count') == 0
    partial = failed and valid and evidence.get('model_output') == 'observed' and type(evidence.get('model_output_event_count')) is int and evidence['model_output_event_count'] > 0
    return {'scope_version': FAILURE_SCOPE, 'evidence_status': 'failed-no-model-output' if absent else 'partial-model-output' if partial else 'unknown-failed-output' if failed else 'recorded', 'withhold_turn_artifacts': absent, 'cli_event_evidence': checked}


def inspect_turn_evidence(run_root, trial_id, turn, *, backend_id):
    """Recheck a failed turn's fixed CLI path against its recorded hash, if any."""
    if not isinstance(trial_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,191}', trial_id) or type(turn.get('turn')) is not int or not 1 <= turn['turn'] <= 3:
        raise ValueError('Invalid failed-turn stream identity')
    if turn.get('status') not in {'failed', 'interrupted'}:
        return {'scope_version': FAILURE_SCOPE, 'evidence_status': 'recorded', 'withhold_turn_artifacts': False}
    if backend_id not in {'local_codex', 'harbor'}:
        return turn_evidence_scope(turn['status'], _unknown('unsupported-backend'))
    recorded = turn.get('cli_event_evidence', {})
    expected = recorded.get('stream_sha256') if isinstance(recorded, dict) else None
    if expected is not None and (not isinstance(expected, str) or not _SHA.fullmatch(expected)):
        return turn_evidence_scope(turn['status'], _unknown('hash-mismatch'))
    path = Path(run_root) / 'trials' / trial_id / ('turn-' + str(turn['turn'])) / 'events.jsonl'
    return turn_evidence_scope(turn['status'], classify_cli_stream(path, expected_sha256=expected))


def persisted_inventory(items, *, kind):
    """Keep bounded hashes from sealed inventories without exposing file names."""
    if not isinstance(items, list) or len(items) > 2048:
        raise ValueError('Persisted artifact inventory exceeds its count limit')
    result = []
    for item in items:
        digest, size = item.get('sha256'), item.get('size')
        if not isinstance(digest, str) or not _SHA.fullmatch(digest) or type(size) is not int or not 0 <= size <= MAX_STREAM_BYTES:
            raise ValueError('Persisted artifact inventory requires bounded hashes and sizes')
        result.append({'sha256': digest, 'size': size, 'kind': kind, 'inventory_source': 'sealed-result'})
    return result
