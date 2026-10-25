"""Mechanical delivery and trusted relation calibration, without aesthetic scores.

This verifier never executes solver code or accepts self-declared quality. A
source container is evidence of delivery, not proof of independent editability.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path


def _png(data: bytes) -> tuple[int, int]:
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('invalid_png_signature')
    pos, size, compressed, ended = 8, None, [], False
    while pos < len(data):
        if pos + 12 > len(data):
            raise ValueError('truncated_png_chunk')
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        end = pos + length + 12
        if end > len(data) or (zlib.crc32(kind + payload) & 0xffffffff) != struct.unpack('>I', data[end - 4:end])[0]:
            raise ValueError('invalid_png_crc')
        if kind == b'IHDR':
            if size is not None or length != 13:
                raise ValueError('invalid_png_ihdr')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if not width or not height or width * height > 32_000_000 or compression or filtering or interlace:
                raise ValueError('unsupported_png_geometry_or_encoding')
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
            valid_depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            if channels is None or depth not in valid_depths[color]:
                raise ValueError('unsupported_png_color')
            size = (width, height)
            expected = height * (1 + (width * channels * depth + 7) // 8)
            if expected > 64 * 1024 * 1024:
                raise ValueError('png_decoded_byte_limit')
        elif kind == b'IDAT':
            compressed.append(payload)
        elif kind == b'IEND':
            ended = True
            if length or end != len(data):
                raise ValueError('invalid_png_end')
            break
        pos = end
    if not size or not ended or not compressed:
        raise ValueError('incomplete_png')
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(b''.join(compressed), expected + 1)
    if len(decoded) != expected or not decoder.eof or decoder.unused_data:
        raise ValueError('invalid_png_pixels')
    stride = expected // size[1]
    if any(decoded[i * stride] > 4 for i in range(size[1])):
        raise ValueError('invalid_png_filter')
    return size


def _svg(data: bytes) -> tuple[ET.Element, tuple[float, float] | None]:
    text = data.decode('utf-8')
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('svg_entities_not_allowed')
    root = ET.fromstring(text)
    if root.tag.split('}')[-1] != 'svg':
        raise ValueError('not_svg_root')
    def number(value):
        match = re.fullmatch(r'\s*([0-9.]+)(?:px)?\s*', value or '')
        return float(match[1]) if match else None
    width, height = number(root.get('width')), number(root.get('height'))
    if width is None or height is None:
        vb = root.get('viewBox', '').replace(',', ' ').split()
        if len(vb) == 4:
            width, height = map(float, vb[2:])
    return root, (width, height) if width is not None and height is not None else None


def _artifact_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('unsafe_artifact_path')
    target = root / rel
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('symlink_artifact')
        cursor = cursor.parent
    if not target.is_file():
        raise ValueError('missing_artifact')
    return target


def grade_delivery(snapshot_dir: Path, case: dict, turn: int) -> dict:
    """Validate declared outputs without reading or executing solver assertions."""
    root = Path(snapshot_dir).resolve()
    if not 1 <= turn <= len(case['turns']):
        raise ValueError('turn_out_of_range')
    limits = case.get('limits', {})
    per_file = limits.get('max_file_bytes', 8 * 1024 * 1024)
    workspace_limit = limits.get('max_workspace_bytes', 32 * 1024 * 1024)
    rows = []
    for artifact in case['turns'][turn - 1]['artifacts']:
        row = {'path': artifact['path'], 'kind': artifact['kind'], 'pass': False}
        try:
            target = _artifact_path(root, artifact['path'])
            if target.stat().st_size > per_file:
                raise ValueError('artifact_byte_limit')
            data = target.read_bytes()
            if not data:
                raise ValueError('empty_artifact')
            row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            fmt = artifact['format']
            dimensions = None
            if fmt == 'png':
                dimensions = _png(data)
            elif fmt == 'svg':
                _, dimensions = _svg(data)
            elif fmt == 'json':
                json.loads(data)
            elif fmt == 'blend':
                if not data.startswith(b'BLENDER'):
                    raise ValueError('invalid_blend_container')
            elif fmt in ('md', 'html', 'py', 'js', 'css', 'txt'):
                data.decode('utf-8')
            # Native formats without a trusted parser have container evidence only.
            row['container_check'] = 'parsed' if fmt in ('png', 'svg', 'json') else 'nonempty_file_only'
            if 'width' in artifact or 'height' in artifact:
                if dimensions is None or tuple(dimensions) != (artifact.get('width'), artifact.get('height')):
                    raise ValueError('artifact_dimensions_mismatch')
            if dimensions:
                row['dimensions'] = list(dimensions)
            row['pass'] = True
        except (ValueError, OSError, ET.ParseError, UnicodeError, struct.error, zlib.error) as error:
            row['error'] = str(error)
        rows.append(row)
    files = [p for p in root.rglob('*') if p.is_file() and not p.is_symlink()]
    total = sum(p.stat().st_size for p in files)
    workspace_pass = total <= workspace_limit and all(p.stat().st_size <= per_file for p in files)
    return {'schema_version': 1, 'turn': turn, 'delivery_pass': bool(rows) and all(r['pass'] for r in rows) and workspace_pass, 'artifacts': rows, 'workspace_bytes': total, 'workspace_limit_pass': workspace_pass, 'quality_status': 'unassessed', 'quality_score': None, 'source_editability_verified': False, 'self_assessment_accepted': False}


def measure_relation(spec: dict) -> dict:
    """Return a bounded measurement for supplied observed coordinates.

    Coordinates need independent evidence before use outside trusted fixtures.
    Passing a measurement does not establish visual quality or user acceptance.
    """
    kind = spec.get('kind')
    result = {'status': 'measured', 'kind': kind, 'quality_status': 'unassessed'}
    try:
        a, b = spec['a'], spec['b']
        if len(a) != 2 or len(b) != 2 or not all(math.isfinite(float(x)) for x in [*a, *b]):
            raise ValueError('invalid_coordinates')
        tolerance = float(spec['tolerance'])
        if tolerance < 0 or not math.isfinite(tolerance):
            raise ValueError('invalid_tolerance')
        if kind == 'shared_baseline':
            distance = abs(float(a[1]) - float(b[1]))
        elif kind == 'anchor_distance':
            distance = math.dist(a, b)
        else:
            return {'status': 'unverifiable', 'reason': 'unsupported_relation', 'quality_status': 'unassessed'}
        result.update(distance=distance, tolerance=tolerance, relation_pass=distance <= tolerance)
    except (KeyError, TypeError, ValueError) as error:
        return {'status': 'unverifiable', 'reason': str(error), 'quality_status': 'unassessed'}
    return result


def _fixture(path: Path, kind: str) -> tuple[dict, dict]:
    root, _ = _svg(path.read_bytes())
    elements = list(root.iter())
    texts = [e for e in elements if e.tag.split('}')[-1] == 'text']
    invariant = {'element_count': len(elements), 'text_content': sorted(''.join(e.itertext()) for e in texts)}
    if kind == 'shared_baseline':
        def point(text):
            e = next(e for e in texts if ''.join(e.itertext()) == text)
            return [float(e.get('x')), float(e.get('y'))]
        spec = {'kind': kind, 'a': point('17 OCT — 22 NOV 2026'), 'b': point('FREE ENTRY'), 'tolerance': 2}
    elif kind == 'anchor_distance':
        circles = [e for e in elements if e.tag.split('}')[-1] == 'circle']
        anchor = circles[-1]
        group = next(e for e in elements if e.tag.split('}')[-1] == 'g')
        transform = re.fullmatch(r'translate\(([\d.-]+)[ ,]+([\d.-]+)\)', group.get('transform', ''))
        path_el = next(e for e in group if e.tag.split('}')[-1] == 'path')
        start = re.match(r'M\s*([\d.-]+)[ ,]+([\d.-]+)', path_el.get('d', ''))
        if not transform or not start:
            raise ValueError('unsupported_fixture_geometry')
        spec = {'kind': kind, 'a': [float(anchor.get('cx')), float(anchor.get('cy'))], 'b': [float(start[1]) + float(transform[1]), float(start[2]) + float(transform[2])], 'tolerance': 1}
    else:
        raise ValueError('unsupported_fixture_measurement')
    return measure_relation(spec), invariant


def calibrate(suite_root: Path) -> dict:
    """Check trusted counterfactual discrimination and nuisance invariance."""
    root = Path(suite_root)
    manifest = json.loads((root / 'calibration' / 'manifest.json').read_text())
    pairs = []
    for pair in manifest['pairs']:
        values, counts = {}, {}
        for label in ('positive', 'negative', 'invariant'):
            ref = pair[label]
            path = _artifact_path((root / 'calibration').resolve(), ref['path'])
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != ref['sha256']:
                raise ValueError('calibration_fixture_hash_mismatch')
            values[label], counts[label] = _fixture(path, pair['measurement'])
        invariant_pass = values['invariant']['relation_pass'] == values['positive']['relation_pass'] and counts['positive'] == counts['negative'] == counts['invariant']
        pairs.append({'id': pair['id'], 'positive_pass': values['positive']['relation_pass'], 'negative_pass': values['negative']['relation_pass'], 'invariance_pass': invariant_pass, 'measurements': values, 'nuisance_checks': counts, 'counts_are_controls_not_quality_scores': True})
    return {'schema_version': 1, 'pass': bool(pairs) and all(p['positive_pass'] and not p['negative_pass'] and p['invariance_pass'] for p in pairs), 'pairs': pairs, 'quality_status': 'unassessed', 'scope': 'trusted fixture geometry only; not a general visual or aesthetic scorer'}
