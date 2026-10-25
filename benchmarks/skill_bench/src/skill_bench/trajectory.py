"""Extract user intent and private attachment evidence without importing trajectories.

Run ``python -m skill_bench.trajectory --help``. No API or external URL is fetched.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path

MAX_ATTACHMENT_BYTES = 64 * 1024 * 1024
_CONTEXT_PREFIXES = ('# AGENTS.md', '<environment_context>', '<skill>', '<INSTRUCTIONS>')
_IMAGE_PATH = re.compile(r'<image\b[^>]*\bpath=["\']([^"\']+)["\']')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _save_attachment(data: bytes, mime: str, output: Path, origin: str) -> dict:
    if len(data) > MAX_ATTACHMENT_BYTES:
        return {'status': 'asset_unavailable', 'reason': 'attachment_byte_limit', 'origin': origin}
    digest = _sha(data)
    suffix = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}.get(mime, '.bin')
    assets = output / 'assets'
    if assets.is_symlink():
        raise ValueError('private_asset_directory_symlink')
    assets.mkdir(mode=0o700, exist_ok=True)
    target = assets / (digest + suffix)
    if target.is_symlink():
        raise ValueError('private_asset_symlink')
    if target.exists() and _sha(target.read_bytes()) != digest:
        raise ValueError('existing_private_asset_hash_mismatch')
    if not target.exists():
        target.write_bytes(data)
        target.chmod(0o600)
    return {'status': 'available', 'path': str(target.relative_to(output)), 'sha256': digest, 'bytes': len(data), 'mime': mime, 'origin': origin, 'visibility': 'private', 'license': 'unconfirmed; not for public redistribution'}


def extract_users(log_paths: list[Path], output_dir: Path) -> dict:
    """Store exact user blocks only, retaining each file/line and attachment hash.

    Input files are not merged into a token total; inherited user blocks may
    repeat across forks and remain attributed to their own source file.
    """
    output = Path(output_dir).resolve()
    if any((parent / '.git').exists() for parent in [output, *output.parents]):
        raise ValueError('Private trajectory extraction must remain outside a Git working tree')
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    output.chmod(0o700)
    messages = []
    sources = []
    malformed = 0
    for log_path in map(Path, log_paths):
        sources.append({'name': log_path.name, 'sha256': _sha(log_path.read_bytes())})
        with log_path.open(encoding='utf-8') as handle:
            for line_no, line in enumerate(handle, 1):
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeError):
                    malformed += 1
                    continue
                payload = row.get('payload', {})
                if row.get('type') != 'response_item' or payload.get('type') != 'message' or payload.get('role') != 'user':
                    continue
                blocks = payload.get('content', [])
                text = '\n'.join(b.get('text', '') for b in blocks if b.get('type') in ('input_text', 'text'))
                local_paths = _IMAGE_PATH.findall(text)
                attachments = []
                for block in blocks:
                    if block.get('type') not in ('input_image', 'image'):
                        continue
                    url = block.get('image_url', '')
                    if isinstance(url, dict):
                        url = url.get('url', '')
                    if isinstance(url, str) and url.startswith('data:image/') and ';base64,' in url:
                        header, encoded = url.split(';base64,', 1)
                        try:
                            if len(encoded) > ((MAX_ATTACHMENT_BYTES + 2) // 3) * 4:
                                raise ValueError('attachment_byte_limit')
                            data = base64.b64decode(encoded, validate=True)
                            attachments.append(_save_attachment(data, header[5:], output, 'embedded_user_image'))
                        except (ValueError, TypeError):
                            attachments.append({'status': 'asset_unavailable', 'reason': 'invalid_embedded_image'})
                    else:
                        attachments.append({'status': 'asset_unavailable', 'reason': 'remote_or_opaque_image_not_fetched'})
                # An embedded payload and a text path can be the same attachment.
                # Only fall back to local files if no image payload was available.
                if not any(a['status'] == 'available' for a in attachments):
                    attachments = []
                    for original in local_paths:
                        path = Path(original)
                        if path.is_file() and path.stat().st_size <= MAX_ATTACHMENT_BYTES:
                            mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(path.suffix.lower(), 'application/octet-stream')
                            attachments.append(_save_attachment(path.read_bytes(), mime, output, original))
                        else:
                            attachments.append({'status': 'asset_unavailable', 'reason': 'local_path_missing_or_too_large', 'origin': original})
                    if not local_paths and any(b.get('type') == 'input_image' for b in blocks):
                        attachments.append({'status': 'asset_unavailable', 'reason': 'opaque_image_not_fetched'})
                messages.append({'source': log_path.name, 'line': line_no, 'event_sha256': _sha(line.encode()), 'user_text_sha256': _sha(text.encode()), 'text': text, 'kind': 'context' if text.lstrip().startswith(_CONTEXT_PREFIXES) else 'intent', 'attachments': attachments})
    target = output / 'users.jsonl'
    target.write_text(''.join(json.dumps(m, ensure_ascii=False) + '\n' for m in messages), encoding='utf-8')
    target.chmod(0o600)
    result = {'schema_version': 1, 'sources': sources, 'intent_messages': sum(m['kind'] == 'intent' for m in messages), 'context_messages': sum(m['kind'] == 'context' for m in messages), 'attachments_available': sum(a['status'] == 'available' for m in messages for a in m['attachments']), 'attachments_unavailable': sum(a['status'] != 'available' for m in messages for a in m['attachments']), 'malformed_lines': malformed, 'counts_are_message_occurrences_not_unique_ancestral_turns': True, 'private_data': True, 'tokens_aggregated': False}
    (output / 'extraction.json').write_text(json.dumps(result, indent=2) + '\n')
    (output / 'extraction.json').chmod(0o600)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description='Extract Codex response_item user-message blocks and private image attachments. Raw text remains private; no tools, assistant output, external URLs, or token totals are imported.')
    parser.add_argument('--log', action='append', required=True, type=Path, help='Exact local JSONL trajectory; repeat for attributed ancestors, without merging inherited usage.')
    parser.add_argument('--output-dir', required=True, type=Path, help='Private directory outside the repository. Existing matching assets are retained.')
    args = parser.parse_args()
    result = extract_users(args.log, args.output_dir)
    print(json.dumps({k: v for k, v in result.items() if k != 'sources'}, indent=2))


if __name__ == '__main__':
    main()
