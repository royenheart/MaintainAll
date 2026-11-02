"""Immutable, content-addressed record store. No overwrite, no symlinks."""
from __future__ import annotations

from pathlib import Path
import json
import os
import tempfile

from .contracts import Record


class StoreError(ValueError):
    pass


class FileRecordStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def seal(self, record: Record) -> Path:
        record = record.with_hash()
        record.validate()
        target = self.root / record.record_id
        if target.exists() or target.is_symlink():
            raise StoreError(f'record already exists: {record.record_id}')
        target.mkdir(parents=False)
        path = target / 'record.json'
        payload = json.dumps(record.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + '\n'
        fd, tmp = tempfile.mkstemp(prefix='.record-', dir=target)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return path

    def list(self) -> list[Record]:
        records = []
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir() or directory.is_symlink():
                continue
            path = directory / 'record.json'
            if not path.is_file():
                continue
            raw = json.loads(path.read_text())
            manifest = __import__('eval_framework.contracts', fromlist=['RunManifest']).RunManifest(**raw['manifest'])
            attempts = tuple(__import__('eval_framework.contracts', fromlist=['Attempt']).Attempt(**item) for item in raw['attempts'])
            record = Record(record_id=raw['record_id'], manifest=manifest, state=raw['state'],
                            attempts=attempts, metrics=raw.get('metrics') or {},
                            evidence=raw.get('evidence') or {}, schema=raw.get('schema', 1),
                            sealed_at=raw.get('sealed_at', ''), record_hash=raw.get('record_hash', ''))
            record.validate()
            records.append(record)
        return records
