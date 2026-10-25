"""Bounded, deterministic diffs of the actual frozen skill snapshots."""
import difflib
import json
from pathlib import Path

from .contracts import artifact_path, checked_file, content_hash

MAX_TEXT_BYTES = 256 * 1024
MAX_PATCH_BYTES = 2 * 1024 * 1024


def _snapshot(root, arm):
    relative = str(artifact_path(arm['skill_snapshot']))
    location = Path(root) / relative
    inventory = arm['files']
    if not isinstance(inventory, dict) or len(inventory) > 4096:
        raise ValueError('Frozen skill inventory is invalid')
    if location.is_symlink() or not location.is_dir():
        raise ValueError('Frozen skill snapshot is missing or linked')
    actual = set()
    for path in location.rglob('*'):
        if path.is_symlink():
            raise ValueError('Frozen skill contains a symbolic link')
        if not path.is_dir():
            actual.add(path.relative_to(location).as_posix())
    if actual != set(inventory):
        raise ValueError('Frozen skill inventory changed')
    if content_hash(json.dumps(inventory, sort_keys=True).encode()) != arm['skill_hash']:
        raise ValueError('Frozen skill identity is inconsistent')
    output, total = {}, 0
    for name, expected in inventory.items():
        artifact_path(name)
        path = checked_file(root, name, location)
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Frozen skill file exceeds its byte ceiling')
        data = path.read_bytes()
        total += len(data)
        if total > 64 * 1024 * 1024 or content_hash(data) != expected:
            raise ValueError('Frozen skill content changed or exceeds its byte ceiling')
        output[name] = data
    return output


def skill_changes(root, manifest):
    """Verify sealed arm identities; omit private/binary/large content explicitly."""
    from .report import _assert_public
    arms = {a['id']: a for a in manifest.get('arms', []) if isinstance(a, dict)}
    if any(not arms.get(a, {}).get('files') or not arms.get(a, {}).get('skill_snapshot') for a in ('previous', 'candidate')):
        return None
    old, new = (_snapshot(root, arms[a]) for a in ('previous', 'candidate'))
    files, patches, size = [], [], 0
    for name in sorted(old.keys() | new.keys()):
        before, after = old.get(name), new.get(name)
        if before == after:
            continue
        record = {'path': name, 'status': 'added' if before is None else 'deleted' if after is None else 'modified',
            'old_sha256': content_hash(before) if before is not None else None,
            'new_sha256': content_hash(after) if after is not None else None, 'omitted_reason': None,
            'added_lines': None, 'removed_lines': None}
        # Names are public identities too; do not expose sensitive names.
        try:
            _assert_public({'path': name})
        except ValueError:
            raise ValueError('A frozen skill filename cannot be published safely') from None
        texts = []
        for data in (before or b'', after or b''):
            if len(data) > MAX_TEXT_BYTES:
                record['omitted_reason'] = 'size-limit'
                break
            try:
                text = data.decode('utf-8')
                if '\x00' in text: raise UnicodeError('Binary content')
            except UnicodeError:
                record['omitted_reason'] = 'binary'
                break
            try:
                _assert_public({'text': text})
            except ValueError:
                record['omitted_reason'] = 'private-content'
                break
            if len(text.splitlines()) > 6000:
                record['omitted_reason'] = 'size-limit'
                break
            texts.append(text)
        if not record['omitted_reason']:
            def quoted(prefix):
                path = prefix + name
                return json.dumps(path, ensure_ascii=True) if any(c.isspace() or c in '\\"' for c in path) else path
            lines = list(difflib.unified_diff(texts[0].splitlines(keepends=True), texts[1].splitlines(keepends=True),
                fromfile=quoted('a/') if before is not None else '/dev/null',
                tofile=quoted('b/') if after is not None else '/dev/null', n=3))
            patch = 'diff --git ' + quoted('a/') + ' ' + quoted('b/') + '\n'
            if before is None: patch += 'new file mode 100644\n'
            if after is None: patch += 'deleted file mode 100644\n'
            patch += ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n' for line in lines)
            length = len(patch.encode())
            if size + length > MAX_PATCH_BYTES:
                record['omitted_reason'] = 'patch-limit'
            else:
                size += length
                patches.append(patch)
                record['added_lines'] = sum(line.startswith('+') for line in lines[2:])
                record['removed_lines'] = sum(line.startswith('-') for line in lines[2:])
        files.append(record)
    patch = ''.join(patches)
    value = {'schema_version': 1, 'scope': 'frozen-skill-snapshots',
        'previous_skill_hash': arms['previous']['skill_hash'], 'candidate_skill_hash': arms['candidate']['skill_hash'],
        'files': files, 'patch': patch, 'patch_sha256': content_hash(patch.encode())}
    validate_changes(value)
    return value


def validate_changes(value):
    """Check the public diff contract independently of HTML and report hashes."""
    import re
    from .report import _assert_public
    fields = {'schema_version','scope','previous_skill_hash','candidate_skill_hash','files','patch','patch_sha256'}
    if not isinstance(value, dict) or set(value) != fields or type(value['schema_version']) is not int or value['schema_version'] != 1 or value['scope'] != 'frozen-skill-snapshots':
        raise ValueError('Invalid skill diff contract')
    for field in ('previous_skill_hash', 'candidate_skill_hash', 'patch_sha256'):
        if not isinstance(value[field], str) or not re.fullmatch('[0-9a-f]{64}', value[field]):
            raise ValueError('Invalid skill diff hash')
    if not isinstance(value['patch'], str) or len(value['patch'].encode()) > MAX_PATCH_BYTES or content_hash(value['patch'].encode()) != value['patch_sha256']:
        raise ValueError('Skill diff patch fingerprint mismatch or byte limit exceeded')
    if not isinstance(value['files'], list) or len(value['files']) > 8192:
        raise ValueError('Invalid skill diff file inventory')
    names = set()
    for item in value['files']:
        if not isinstance(item, dict) or set(item) != {'path','status','old_sha256','new_sha256','omitted_reason','added_lines','removed_lines'}:
            raise ValueError('Invalid skill diff file record')
        artifact_path(item['path'])
        if item['path'] in names or item['status'] not in ('added','deleted','modified') or item['omitted_reason'] not in (None,'private-content','binary','size-limit','patch-limit'):
            raise ValueError('Invalid skill diff file identity or status')
        names.add(item['path'])
        for field in ('old_sha256','new_sha256'):
            if item[field] is not None and (not isinstance(item[field], str) or not re.fullmatch('[0-9a-f]{64}', item[field])):
                raise ValueError('Invalid skill diff file hash')
        for field in ('added_lines','removed_lines'):
            if item[field] is not None and (type(item[field]) is not int or item[field] < 0):
                raise ValueError('Invalid skill diff line count')
    _assert_public(value)
    return value


def validate_report_changes(public):
    for experiment in public.get('experiments', []):
        if 'skill_changes' not in experiment:
            continue
        change = validate_changes(experiment['skill_changes'])
        hashes = {a['id']: a.get('skill_hash') for a in experiment.get('arms', [])}
        if hashes.get('previous') != change['previous_skill_hash'] or hashes.get('candidate') != change['candidate_skill_hash']:
            raise ValueError('Skill diff does not match the evaluated arm snapshots')
