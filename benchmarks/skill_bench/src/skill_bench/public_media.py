"""Lossless PNG publication derivatives; source and review hashes stay intact."""
from __future__ import annotations

import struct
import re
import zlib

METADATA_CHUNKS = {b'tEXt', b'zTXt', b'iTXt', b'eXIf', b'tIME'}
TRANSFORMATION = 'png-metadata-removal-v1'


def validate_derivation(item: dict) -> None:
    fields = {'source_sha256', 'source_size', 'transformation'}
    if not fields.intersection(item):
        return
    change = item.get('transformation')
    if (not fields.issubset(item) or not isinstance(item['source_sha256'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', item['source_sha256']) or item['source_sha256'] == item['sha256']
            or type(item['source_size']) is not int or item['source_size'] <= item['size']
            or not isinstance(change, dict) or set(change) != {'id', 'removed_chunks'}
            or change['id'] != TRANSFORMATION or not isinstance(change['removed_chunks'], list)
            or not change['removed_chunks'] or any(not isinstance(tag, str) or tag not in {k.decode('ascii') for k in METADATA_CHUNKS} for tag in change['removed_chunks'])):
        raise ValueError('Invalid public image derivation record')


def strip_png_metadata(data: bytes) -> tuple[bytes, list[str]]:
    """Remove text, EXIF and timestamps; retain all rendering chunks verbatim.

    Public callers also run the bounded PNG pixel/container validator. Keeping
    compressed image and color-profile bytes avoids re-rendering scored work.
    """
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid PNG signature')
    output, removed, pos = [data[:8]], set(), 8
    while pos < len(data):
        if pos + 12 > len(data):
            raise ValueError('Truncated PNG chunk')
        size = struct.unpack('>I', data[pos:pos + 4])[0]
        end = pos + size + 12
        if end > len(data):
            raise ValueError('Truncated PNG payload')
        kind = data[pos + 4:pos + 8]
        if zlib.crc32(data[pos + 4:end - 4]) & 0xffffffff != struct.unpack('>I', data[end - 4:end])[0]:
            raise ValueError('Invalid PNG checksum')
        if kind in METADATA_CHUNKS:
            removed.add(kind.decode('ascii'))
        else:
            output.append(data[pos:end])
        pos = end
    return b''.join(output), sorted(removed)
