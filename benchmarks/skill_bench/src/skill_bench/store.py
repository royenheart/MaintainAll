"""Immutable evidence and durable experiment events."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def private_directory(path, must_be_new=False):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Private evidence paths cannot traverse symbolic links")
    if any((p / ".git").exists() for p in (path, *path.parents)):
        raise ValueError("Private run evidence must stay outside repositories")
    if must_be_new and path.exists():
        raise ValueError("Run output already exists; evidence cannot be overwritten")
    path.mkdir(parents=True, exist_ok=not must_be_new, mode=0o700)
    path.chmod(0o700)
    return path.resolve()


def write_immutable(path, value):
    """Publish a complete record once; identical writes are idempotent."""
    path = Path(path)
    data = encoded(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("An immutable record cannot be a symlink")
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("An immutable record cannot be replaced")
        return digest(data)
    fd, temporary = tempfile.mkstemp(prefix=".evidence-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != data:
                raise ValueError("An immutable record cannot be replaced") from None
    finally:
        os.unlink(temporary)
    return digest(data)


def write_projection(path, value):
    """Derived state is replaceable; source events and results are not."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Projection cannot be a symlink")
    fd, temporary = tempfile.mkstemp(prefix=".projection-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def append_event(root, event, max_calls=None):
    """Persist a call reservation before launch, serialized across writers."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "events.jsonl"
    if path.is_symlink():
        raise ValueError("Event ledger cannot be a symlink")
    with path.open("a+", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            rows = read_events(root)
            if event.get("type") == "call_reserved":
                calls = [e for e in rows if e["type"] == "call_reserved"]
                if any((e.get("trial_id"), e.get("turn")) ==
                       (event.get("trial_id"), event.get("turn")) for e in calls):
                    raise ValueError("This call has already been reserved; silent retries are forbidden")
                if max_calls is None or len(calls) >= max_calls:
                    raise ValueError("The invocation budget is exhausted or unspecified")
            row = {**event, "sequence": len(rows), "timestamp_epoch": time.time(),
                   "previous_sha256": rows[-1]["sha256"] if rows else None}
            row["sha256"] = digest(encoded(row))
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            return row
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_events(root):
    path = Path(root) / "events.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines(keepends=True):
        if not line.endswith("\n"):
            raise ValueError("Truncated event record")
        try:
            row = json.loads(line)
            claimed = row.pop("sha256")
        except (ValueError, KeyError, TypeError):
            raise ValueError("Invalid event record") from None
        if claimed != digest(encoded(row)):
            raise ValueError("Event content hash mismatch")
        if row.get("sequence") != len(rows) or row.get("previous_sha256") != (rows[-1]["sha256"] if rows else None):
            raise ValueError("Event sequence/hash chain mismatch")
        rows.append({**row, "sha256": claimed})
    return rows


def load_results(root):
    results = []
    for path in sorted((Path(root) / "trials").glob("*/result.json")):
        if path.is_symlink() or path.parent.is_symlink() or path.stat().st_nlink != 1:
            raise ValueError("Evidence record cannot be a symlink")
        seal_path = path.with_name('result-seal.json')
        if not seal_path.is_file() or seal_path.is_symlink():
            raise ValueError("Evidence result seal is missing")
        if digest(path.read_bytes()) != json.loads(seal_path.read_text()).get('sha256'):
            raise ValueError("Evidence result seal mismatch")
        result = json.loads(path.read_text())
        if result.get('trial_id') != path.parent.name or result.get('status') not in {'completed', 'failed', 'unsupported', 'interrupted'}:
            raise ValueError("Evidence trial identity or status mismatch")
        results.append(result)
    return results


def state(root, manifest):
    """Completion comes from every planned trial's terminal evidence."""
    events = read_events(root)
    results = {row["trial_id"]: row for row in load_results(root)}
    expected = {row["trial_id"] for row in manifest["schedule"]}
    if any(r['status'] == 'interrupted' for r in results.values()):
        phase = 'interrupted'
    elif expected and expected.issubset(results):
        phase = "completed" if all(results[i]["status"] == "completed" for i in expected) else "completed_with_failures"
    elif any(row["type"] == "run_finished" for row in events):
        phase = "interrupted"
    elif any(row["type"] == "run_started" for row in events):
        phase = "running"
    else:
        phase = "prepared"
    return {"state": phase, "planned_trials": len(expected), "recorded_trials": len(results),
            "reserved_calls": sum(e["type"] == "call_reserved" for e in events),
            "completed_trials": sum(r["status"] == "completed" for r in results.values()),
            "quality_status": "unassessed", "automatic_quality_pass": None}
