"""Export anonymous, hash-checked artifacts and freeze independent review records.

The exporter never imports raw model events, final messages, credentials, or thread
identifiers. A private map under the run directory is the only arm lookup.
"""
from __future__ import annotations

import hashlib
import hmac
import base64
import html
import itertools
import json
import os
from pathlib import Path, PurePosixPath
import random
import re
import shutil
import stat
import tempfile
from typing import Any
import zlib

MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SCORES = {0, 1, 2, "unverifiable"}
OUTCOMES = {"win", "tie", "loss", "undetermined"}
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_NOTE_BYTES = 256 * 1024
MAX_NOTE_TOTAL_BYTES = 2 * 1024 * 1024
_SHA = re.compile(r"^[0-9a-f]{64}$")


def canonical_hash(value: Any) -> str:
    """Return a stable SHA-256 fingerprint without timestamps or JSON whitespace."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def blind_entry_id(review_id: str, trial_id: str, private_key: str) -> str:
    """Bind a trial to an opaque ID that requires a run-private random key."""
    if not isinstance(private_key, str) or not _SHA.fullmatch(private_key):
        raise ValueError("Anonymous review mapping requires a valid private blind key")
    payload = json.dumps({"review": review_id, "trial": trial_id}, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(bytes.fromhex(private_key), payload, hashlib.sha256).hexdigest()[:24]


def _blind_key(root: Path) -> dict:
    """Create or read the immutable private key; never copy it to a packet."""
    directory = root / "reviews"
    if directory.is_symlink():
        raise ValueError("Private review directory cannot be a symbolic link")
    directory.mkdir(exist_ok=True)
    directory.chmod(0o700)
    path = directory / "blind-key.json"
    if not path.exists():
        secret = os.urandom(32).hex()
        value = {"schema_version": 1, "private_key": secret, "blind_key_id": hashlib.sha256(bytes.fromhex(secret)).hexdigest()[:16]}
        try:
            _write_json(path, value, private=True)
        except FileExistsError:
            pass
    value = read_json(root, "reviews/blind-key.json")
    secret = value.get("private_key")
    if value.get("schema_version") != 1 or not isinstance(secret, str) or not _SHA.fullmatch(secret) or value.get("blind_key_id") != hashlib.sha256(bytes.fromhex(secret)).hexdigest()[:16]:
        raise ValueError("Invalid run-private blind key")
    path.chmod(0o600)
    return value


def validate_packet_mapping(packet: dict, mapping: dict) -> None:
    """Reject a modified blind packet before freezing or importing its ratings."""
    if mapping.get("review_id") != packet.get("review_id") or mapping.get("packet_sha256") != canonical_hash(packet):
        raise ValueError("Anonymous packet fingerprint differs from its private frozen mapping")
    if 'evidence_scope' in packet or 'evidence_scope' in mapping:
        if packet.get('evidence_scope') != 'failed-turn-v1' or mapping.get('evidence_scope') != packet['evidence_scope']:
            raise ValueError('Failed-turn evidence scope differs from its private mapping')
    if ('source_revision' in packet) != ('source_revision' in mapping) or packet.get('source_revision') != mapping.get('source_revision'):
        raise ValueError('Reviewed source revision differs from its private mapping')
    if packet.get('source_revision') is not None and (not isinstance(packet['source_revision'], str) or not _SHA.fullmatch(packet['source_revision'])):
        raise ValueError('Reviewed source revision requires a full evidence fingerprint')
    if 'case_selection' in packet or 'case_selection' in mapping:
        selection = packet.get('case_selection')
        if not isinstance(selection, dict) or set(selection) != {'schema_version', 'case_ids', 'policy'} or selection != mapping.get('case_selection') or selection['schema_version'] != 1 or selection['policy'] != 'all-cases-as-completed':
            raise ValueError('Selected review scope differs from its private mapping')
        identifiers = selection['case_ids']
        if not isinstance(identifiers, list) or not identifiers or any(not isinstance(value, str) for value in identifiers) or identifiers != sorted(set(identifiers)) or set(identifiers) != {entry['case_id'] for entry in packet.get('entries', [])}:
            raise ValueError('Selected review entries differ from the frozen case subset')
    secret = mapping.get("private_key")
    if not isinstance(secret, str) or not _SHA.fullmatch(secret) or mapping.get("blind_key_id") != hashlib.sha256(bytes.fromhex(secret)).hexdigest()[:16]:
        raise ValueError("Anonymous mapping has no valid private blind key identity")
    entries = packet.get("entries", [])
    private_entries = mapping.get("entries", {})
    if len({entry["id"] for entry in entries}) != len(entries) or {entry["id"] for entry in entries} != set(private_entries):
        raise ValueError("Anonymous entries differ from their private mapping")
    for entry in entries:
        private = private_entries[entry["id"]]
        if entry["id"] != blind_entry_id(packet["review_id"], private["trial_id"], secret) or any(entry[key] != private[key] for key in ("case_id", "repeat")):
            raise ValueError("Anonymous entry fingerprint differs from its private mapping")


def execution_state(events: list[dict] | None) -> dict:
    """Read terminal coverage from an already hash-chain-validated ledger.

    Only execution event types and trial IDs are consumed. Event messages and
    reasons are never promoted into review or report content.
    """
    if events is None:
        events = []
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise ValueError("Execution coverage requires validated ledger events")
    activity = {"run_started", "call_reserved", "turn_started", "turn_completed", "trial_completed"}
    last_activity = max((index for index, event in enumerate(events) if event.get("type") in activity), default=-1)
    last_finished = max((index for index, event in enumerate(events) if event.get("type") == "run_finished"), default=-1)
    attempted = {event["trial_id"] for event in events if event.get("type") in {"call_reserved", "turn_started"} and isinstance(event.get("trial_id"), str)}
    return {"closed": last_finished >= 0 and last_finished > last_activity, "attempted_trial_ids": attempted}


def missing_trial_observation(case: dict, trial_id: str, terminal: dict) -> dict:
    """Represent absent records as evidence gaps, without fabricating results."""
    if terminal.get("closed") is not True:
        raise ValueError("Missing results require a closed execution ledger")
    attempted = trial_id in terminal["attempted_trial_ids"]
    status = "interrupted" if attempted else "not_attempted"
    reason = "Execution ledger closed after a call reservation or turn start, but no sealed result was recorded." if attempted else "Execution ledger closed without a recorded call reservation or turn start for this planned trial."
    return {"status": status, "result_record": "missing", "absence_reason": reason, "turns": [{"turn": number, "status": status, "artifacts": [], "evidence_status": "missing-result", "absence_reason": reason, "reservation_observed": attempted} for number in range(1, len(case.get("turns", [])) + 1)]}


def checked_file(root: Path, relative: str, *, expected_hash: str | None = None, expected_size: int | None = None, max_bytes: int = MAX_JSON_BYTES) -> tuple[Path, bytes]:
    """Read an ordinary file inside root; reject traversal, symlinks and mismatch."""
    if root.is_symlink():
        raise ValueError("Symbolic roots are not exportable")
    if not isinstance(relative, str) or "\\" in relative or "\x00" in relative:
        raise ValueError("Invalid relative artifact path")
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or any(part in {"..", ".", ""} for part in relative.split("/")):
        raise ValueError("Artifact path must remain inside its declared root")
    # Check lexical components before resolve so a symlink to an internal target
    # is rejected too; merely checking the resolved target would accept it.
    current = root
    for component in path.parts:
        current = current / component
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError("Symbolic links are not exportable")
    if not stat.S_ISREG(current.stat().st_mode):
        raise ValueError("Artifact is not an ordinary file")
    size = current.stat().st_size
    if type(max_bytes) is not int or max_bytes < 1 or size > max_bytes:
        raise ValueError("Artifact exceeds the export byte limit")
    data = current.read_bytes()
    if len(data) > max_bytes:
        raise ValueError("Artifact grew beyond its export byte limit")
    if expected_size is not None and (type(expected_size) is not int or len(data) != expected_size):
        raise ValueError("Artifact size does not match the immutable inventory")
    digest = hashlib.sha256(data).hexdigest()
    if expected_hash is not None and (not _SHA.fullmatch(expected_hash) or digest != expected_hash):
        raise ValueError("Artifact hash does not match the immutable inventory")
    return current, data


def read_json(root: Path, relative: str) -> dict:
    _, data = checked_file(root, relative)
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _write_json(path: Path, value: Any, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    if private:
        path.chmod(0o600)


def _raster_suffix(path: str, data: bytes) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    magic = {
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"),
        ".jpeg": data.startswith(b"\xff\xd8\xff"),
        ".gif": data.startswith((b"GIF87a", b"GIF89a")),
        ".webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }
    if suffix not in MEDIA_SUFFIXES or not magic.get(suffix):
        raise ValueError("Declared preview is not a supported raster image")
    return ".jpg" if suffix == ".jpeg" else suffix


def preview_validation(path: str, data: bytes) -> dict:
    """Check bounded static PNG contents; other raster checks are signature-only.

    Callers must check immutable file integrity before calling this function.
    An unsupported/invalid solver preview is withheld, never a quality score.
    """
    try:
        suffix = _raster_suffix(path, data)
    except ValueError:
        return {"allowed": False, "withheld_reason": "Raster signature does not match a supported declared image suffix."}
    if suffix == ".png":
        from .grading import _png
        try:
            width, height = _png(data)
        except (ValueError, zlib.error):
            return {"allowed": False, "withheld_reason": "PNG container or pixel data did not pass the bounded static-lane check."}
        return {"allowed": True, "suffix": suffix, "container_check": "png-container-and-pixels", "width": width, "height": height}
    return {"allowed": True, "suffix": suffix, "container_check": "signature-only"}


def _copy_media(root: Path, staging: Path, item: dict, *, max_file_bytes: int, total: list[int], max_total_bytes: int, allow_invalid: bool = False) -> dict:
    relative = item.get("snapshot", item.get("path"))
    _, data = checked_file(root, relative, expected_hash=item.get("sha256"), expected_size=item.get("size"), max_bytes=max_file_bytes)
    if not item.get("sha256"):
        raise ValueError("Every exported image requires an inventory hash")
    digest = hashlib.sha256(data).hexdigest()
    validation = preview_validation(relative, data)
    if not validation["allowed"]:
        if not allow_invalid:
            raise ValueError(validation["withheld_reason"])
        return {"sha256": digest, "size": len(data), "kind": "withheld-preview", "withheld_reason": validation["withheld_reason"]}
    suffix = validation["suffix"]
    target = "media/" + digest + suffix
    destination = staging / target
    if not destination.exists():
        total[0] += len(data)
        if total[0] > max_total_bytes:
            raise ValueError("Review package exceeds the aggregate byte limit")
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(data)
    result = {"path": target, "sha256": digest, "size": len(data), "kind": "preview", "container_check": validation["container_check"]}
    for field in ("width", "height", "format"):
        if field in item and isinstance(item[field], (str, int)):
            result[field] = item[field]
    for field in ("width", "height"):
        if field in validation:
            result[field] = validation[field]
    return result


def _safe_text(text: str, arm_names: list[str]) -> str:
    # A notes/process view is optional and distinct from artifact scoring. Fail
    # closed instead of silently rewriting quoted model claims or hiding leaks.
    forbidden = [r"(?i)(?:api[_ -]?key|access[_ -]?token|authorization|bearer)\s*[:=]", r"(?i)\bbearer\s+[a-z0-9._-]+", r"(?i)\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", r"(?:/home/|/root/|\.codex/|\.agents/skills/)"]
    names = "(?:" + "|".join(re.escape(name) for name in arm_names if name) + ")"
    if names != "(?:)":
        # Ordinary phrases such as "previous selected direction" describe the
        # task. Explicit experimental labels and winner claims reveal an arm.
        context = r"(?:arm|baseline|skill(?:[ _-]+version)?|version|实验臂|基线|技能版本|版本)"
        forbidden += [r"(?i)\b" + context + r"\s*[:=\"' _-]*\b" + names + r"\b", r"(?i)\b" + names + r"\s+(?:arm|baseline|skill|version|wins?|beats?|outperforms?)\b"]
    if any(re.search(pattern, text) for pattern in forbidden):
        raise ValueError("Declared review notes contain private or arm-identifying text")
    return text


def sanitize_v2_note(text: str, arm_names: list[str]) -> tuple[str, dict]:
    """Mask only host-local path tokens, retaining all evaluative statements."""
    credentials = (r'(?i)(?:api[_ -]?key|access[_ -]?token|authorization|bearer)[\"\x27\s]*[:=]', r'(?i)\bbearer\s+[a-z0-9._-]+')
    if any(re.search(pattern, text) for pattern in credentials):
        raise ValueError('Declared review notes contain credential-like text')
    prefix = r'(?:/home/|/root/|~/(?:\.codex/|\.agents/skills/)|\.codex/|\.agents/skills/)'
    quoted = r'([\"\x27])(' + prefix + r'[^\r\n]*?)\1'
    safe = re.sub(quoted, lambda match: match[1] + '[local path]' + match[1], text)
    safe = re.sub(prefix + r'[^\s`\"\x27<>\]\[(){};,]*', '[local path]', safe)
    _safe_text(safe, arm_names)
    return safe, {'id': 'local-path-redaction-v1', 'changed': safe != text}


def validate_declared_note(note: dict, *, media_root=None, require_path=False) -> bytes:
    """Check bounded plain-text task output, keeping solver claims unverified."""
    if not isinstance(note, dict) or note.get('kind') != 'notes' or note.get('format') not in {'md', 'txt'} or note.get('source') != 'frozen-case-declared-notes':
        raise ValueError('Text evidence must be a declared Markdown or plain-text note')
    text, name = note.get('text'), note.get('name')
    if not isinstance(text, str) or not isinstance(name, str) or not 1 <= len(name) <= 256 or Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name or Path(name).suffix.lower() not in {'.md', '.txt'}:
        raise ValueError('Declared text evidence has an unsafe name or content')
    _safe_text(text, [])
    data = text.encode('utf-8')
    if len(data) > MAX_NOTE_BYTES or not isinstance(note.get('sha256'), str) or not _SHA.fullmatch(note['sha256']) or hashlib.sha256(data).hexdigest() != note['sha256']:
        raise ValueError('Declared text evidence exceeds its byte limit or hash seal')
    if any(key in note for key in ('source_sha256', 'source_size', 'transformation')):
        transformation = note.get('transformation')
        if not isinstance(note.get('source_sha256'), str) or not _SHA.fullmatch(note['source_sha256']) or type(note.get('source_size')) is not int or not 0 <= note['source_size'] <= MAX_NOTE_BYTES or not isinstance(transformation, dict) or set(transformation) != {'id', 'changed'} or transformation['id'] != 'local-path-redaction-v1' or type(transformation['changed']) is not bool or transformation['changed'] != (note['source_sha256'] != note['sha256']):
            raise ValueError('Declared text source identity or transformation metadata is invalid')
        if not transformation['changed'] and note['source_size'] != len(data):
            raise ValueError('Unchanged declared text source size differs from its copied bytes')
    if require_path or 'path' in note:
        if note.get('path') != 'text/' + note['sha256'] + '.txt' or type(note.get('size')) is not int or note['size'] != len(data):
            raise ValueError('Declared text evidence must use its content-addressed path and size')
        if media_root is not None:
            checked_file(Path(media_root), note['path'], expected_hash=note['sha256'], expected_size=note['size'], max_bytes=MAX_NOTE_BYTES)
    return data


def _selected_results(root: Path, trial_ids: list[str]) -> list[dict]:
    """Read only selected ordinary result records with the standard seal checks."""
    results = []
    for trial_id in sorted(trial_ids):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', trial_id) or trial_id in {'.', '..'}:
            raise ValueError('Unsafe selected trial identity')
        relative = 'trials/' + trial_id + '/result.json'
        target = root / relative
        if not target.exists() and not target.is_symlink():
            continue
        path, data = checked_file(root, relative)
        if path.stat().st_nlink != 1:
            raise ValueError('Evidence record cannot be a hard link')
        seal_path = root / 'trials' / trial_id / 'result-seal.json'
        if not seal_path.is_file() or seal_path.is_symlink():
            raise ValueError('Evidence result seal is missing')
        seal = read_json(root, 'trials/' + trial_id + '/result-seal.json')
        if hashlib.sha256(data).hexdigest() != seal.get('sha256'):
            raise ValueError('Evidence result seal mismatch')
        result = json.loads(data)
        if not isinstance(result, dict) or result.get('trial_id') != trial_id or result.get('status') not in {'completed', 'failed', 'unsupported', 'interrupted'}:
            raise ValueError('Evidence trial identity or status mismatch')
        results.append(result)
    return results


def export_review(run_dir: str | Path, destination: str | Path, *, seed: int, view: str = "artifact-only", max_file_bytes: int = 8 * 1024 * 1024, max_total_bytes: int = 64 * 1024 * 1024, allow_private: bool = False, regrade_path=None, selected_cases: list[str] | None = None, evidence_scope='legacy') -> dict:
    """Export raw-size raster comparisons with private randomized arm mapping.

    ``artifact-only`` excludes explanations. ``notes-process`` also includes only
    notes declared by the current frozen case turn, after leak checks. The distinct
    ``notes-process-v2`` condition adds bounded, hash-citable text files. An
    explicit legacy ``review_safe: false`` remains excluded; solver flags do not
    grant export permission. Raw traces and final messages remain excluded.
    Explicit case selection is bound to a new packet scope; it never changes
    full-export defaults or permits unsealed selected outcomes.
    """
    if view not in {"artifact-only", "notes-process", "notes-process-v2"} or type(seed) is not int:
        raise ValueError("Use an integer seed and a supported review view")
    if evidence_scope not in {'legacy', 'failed-turn-v1'}:
        raise ValueError('Unsupported failed-turn evidence scope')
    root, dest = Path(run_dir), Path(destination)
    if dest.exists() or dest.is_symlink() or root.is_symlink():
        raise ValueError("Review destination must be new and run root ordinary")
    from .experiment import load_experiment
    from .store import load_results, read_events
    manifest = load_experiment(root)
    schedules = manifest.get("schedule", [])
    cases = {case["id"]: case for case in manifest.get("cases", [])}
    selection = None
    if selected_cases is not None:
        if not isinstance(selected_cases, list) or not selected_cases or any(not isinstance(value, str) for value in selected_cases) or len(set(selected_cases)) != len(selected_cases) or not set(selected_cases).issubset(cases):
            raise ValueError('Review selection must be a nonempty unique list of frozen case IDs')
        selection = {'schema_version': 1, 'case_ids': sorted(selected_cases), 'policy': 'all-cases-as-completed'}
        cases = {key: value for key, value in cases.items() if key in selected_cases}
        schedules = [row for row in schedules if row['case_id'] in cases]
        if {row['case_id'] for row in schedules} != set(selected_cases):
            raise ValueError('Selected frozen cases have no scheduled trials')
    loaded_results = {result["trial_id"]: result for result in (_selected_results(root, [row['trial_id'] for row in schedules]) if selection else load_results(root))}
    revision = None
    if regrade_path is not None:
        from .runner import load_regrade
        revision = load_regrade(root, regrade_path)
        loaded_results = {result['trial_id']: result for result in revision['results']}
    if selection:
        selected_trials = {row['trial_id'] for row in schedules}
        loaded_results = {key: value for key, value in loaded_results.items() if key in selected_trials}
    missing = {row["trial_id"] for row in schedules} - set(loaded_results)
    terminal = {"closed": False, "attempted_trial_ids": set()}
    if missing:
        if (root / "events.jsonl").exists():
            checked_file(root, "events.jsonl")
        terminal = execution_state(read_events(root))
        if not terminal["closed"]:
            raise ValueError("Missing results require a closed execution ledger before review export")
    private_case = any(case.get("visibility") == "private" or any(asset.get("visibility") == "private" for asset in case.get("assets", case.get("attachments", []))) for case in cases.values())
    if private_case and not allow_private:
        raise ValueError("Private cases require explicit local-private review export")
    private_packet = private_case or (allow_private and any(asset.get("visibility") == "private" for case in cases.values() for asset in case.get("assets", case.get("attachments", []))))
    trial_ids = [row["trial_id"] for row in schedules]
    if len(trial_ids) != len(set(trial_ids)):
        raise ValueError("Duplicate trial IDs in schedule")
    arm_names = [arm if isinstance(arm, str) else arm.get("id", "") for arm in manifest.get("arms", [])]
    identity = {"manifest": manifest, "seed": seed, "view": view}
    if evidence_scope != 'legacy':
        identity['evidence_scope'] = evidence_scope
    if selection:
        identity['case_selection'] = selection
    if revision:
        identity['source_revision'] = revision['id']
    review_id = canonical_hash(identity)[:24]
    private_map_path = root / "reviews" / (review_id + ".arm-map.json")
    if private_map_path.parent.is_symlink():
        raise ValueError("Private mapping directory cannot be a symbolic link")
    if private_map_path.exists():
        raise ValueError("This review export already has a private arm mapping")
    blind_key = _blind_key(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".review-export-", dir=dest.parent))
    packet = {"schema_version": 1, "review_id": review_id, "view": view, "privacy": "local-private" if private_packet else "public-sanitized", "entries": [], "pairs": [], "references": [], "limitations": ["Artifact review is independent of mechanical delivery checks.", "No automatic aesthetic pass is inferred from model explanations.", "Repeated turn atoms are not independent samples."]}
    if view == 'notes-process-v2':
        packet['notes_scope_version'] = 2
        packet['limitations'].append('Declared text can be cited as task output; self-evaluation and explanatory captions remain solver claims.')
    private = {"schema_version": 1, "review_id": review_id, "seed": seed, "view": view, "entries": {}, "private_key": blind_key["private_key"], "blind_key_id": blind_key["blind_key_id"]}
    if evidence_scope != 'legacy':
        packet['evidence_scope'] = private['evidence_scope'] = evidence_scope
        packet['limitations'].append('Failed turns with verified absent model output withhold persisted files; observed output on failed turns remains a partial snapshot and does not prove that every file changed.')
    if selection:
        packet['case_selection'] = private['case_selection'] = selection
    # None identifies original sealed solver evidence. A regrade ID identifies
    # the exact independently captured evidence the reviewer actually viewed.
    packet['source_revision'] = private['source_revision'] = revision['id'] if revision else None
    total = [0]
    note_total = 0
    rng = random.Random(seed)
    groups: dict[tuple[str, int], list[str]] = {}
    try:
        shuffled = list(schedules)
        rng.shuffle(shuffled)
        for row in shuffled:
            trial_id = row["trial_id"]
            case = cases[row["case_id"]]
            result = loaded_results.get(trial_id) or missing_trial_observation(case, trial_id, terminal)
            entry_id = blind_entry_id(review_id, trial_id, blind_key["private_key"])
            entry = {"id": entry_id, "case_id": row["case_id"], "case_version": case.get("version", "unknown"), "repeat": row["repeat"], "status": result["status"], "result_record": "present" if trial_id in loaded_results else "missing", "turns": [], "atoms": [{key: atom[key] for key in ("id", "dimension", "active_turns", "criterion", "requirement_ids", "depends_on", "anchors", "evidence") if key in atom} for atom in case.get("atoms", [])]}
            entry["requirements"] = [{key: requirement[key] for key in ("id", "turn", "quote") if key in requirement} for requirement in case.get("requirements", [])]
            entry["prompts"] = [turn["prompt"] for turn in case.get("turns", [])]
            for turn in result.get("turns", []):
                exported = {"turn": turn["turn"], "status": turn.get("status", result["status"]), "evidence_status": turn.get("evidence_status", "recorded"), "artifacts": []}
                withhold = False
                if evidence_scope != 'legacy' and exported['evidence_status'] != 'missing-result':
                    from .failure_evidence import inspect_turn_evidence, persisted_inventory
                    scope = inspect_turn_evidence(root, trial_id, {**turn, 'status': exported['status']}, backend_id=result.get('backend', {}).get('id'))
                    exported['evidence_status'] = scope['evidence_status']
                    if 'cli_event_evidence' in scope:
                        exported['cli_event_evidence'] = scope['cli_event_evidence']
                    withhold = scope['withhold_turn_artifacts']
                    if withhold:
                        exported['persisted_artifact_inventory'] = persisted_inventory(turn.get('artifacts', []), kind='persisted-artifact-withheld')
                        exported['persisted_source_proof_inventory'] = persisted_inventory([image for proof in turn.get('source_verification', []) for image in proof.get('rendered', {}).values()], kind='persisted-reopen-withheld')
                delivery = turn.get("delivery", {})
                delivery_pass = delivery.get("delivery_pass", delivery.get("passed")) if isinstance(delivery, dict) else None
                status_value = {"status": exported["status"], "trial_status": result["status"], "turn": turn["turn"], "evidence_status": exported["evidence_status"], "delivery_pass": delivery_pass if type(delivery_pass) is bool else None}
                if evidence_scope != 'legacy':
                    status_value.update({key: exported[key] for key in ('cli_event_evidence', 'persisted_artifact_inventory', 'persisted_source_proof_inventory') if key in exported})
                if exported["evidence_status"] == "missing-result":
                    exported["absence_reason"] = turn["absence_reason"]
                    status_value.update(absence_reason=turn["absence_reason"], reservation_observed=turn["reservation_observed"])
                declared = {item["path"]: item for item in case.get("turns", [])[turn["turn"] - 1].get("artifacts", [])} if 1 <= turn["turn"] <= len(case.get("turns", [])) else {}
                for artifact in [] if withhold else turn.get("artifacts", []):
                    specification = declared.get(artifact.get("path"), {})
                    suffix = PurePosixPath(artifact.get("snapshot", artifact.get("path", ""))).suffix.lower()
                    if suffix in MEDIA_SUFFIXES:
                        media = _copy_media(root / "trials" / trial_id, staging, artifact, max_file_bytes=max_file_bytes, total=total, max_total_bytes=max_total_bytes, allow_invalid=True)
                        media["name"] = artifact["path"] if artifact.get("path") in declared else "additional-preview"
                        if media.get("withheld_reason"):
                            exported.setdefault("withheld_previews", []).append(media)
                        else:
                            exported["artifacts"].append(media)
                    elif view in {"notes-process", "notes-process-v2"} and specification.get("kind") == "notes" and artifact.get("review_safe") is not False:
                        _, data = checked_file(root / "trials" / trial_id, artifact["snapshot"], expected_hash=artifact.get("sha256"), expected_size=artifact.get("size"), max_bytes=min(max_file_bytes, MAX_NOTE_BYTES) if view == 'notes-process-v2' else max_file_bytes)
                        if not artifact.get("sha256"):
                            raise ValueError("Every exported note requires an inventory hash")
                        total[0] += len(data)
                        if total[0] > max_total_bytes:
                            raise ValueError("Review package exceeds the aggregate byte limit")
                        text = data.decode('utf-8')
                        transformation = None
                        if view == 'notes-process-v2':
                            text, transformation = sanitize_v2_note(text, arm_names)
                        else:
                            text = _safe_text(text, arm_names)
                        exported_data = text.encode('utf-8')
                        note = {"text": text, "name": specification["path"], "kind": specification["kind"], "format": specification["format"], "sha256": hashlib.sha256(exported_data).hexdigest(), "source": "frozen-case-declared-notes"}
                        if view == 'notes-process-v2':
                            note.update(path='text/' + note['sha256'] + '.txt', size=len(exported_data), source_sha256=hashlib.sha256(data).hexdigest(), source_size=len(data), transformation=transformation)
                            validate_declared_note(note, require_path=True)
                            note_total += len(data)
                            if note_total > MAX_NOTE_TOTAL_BYTES:
                                raise ValueError('Review declared text exceeds its aggregate byte limit')
                            output = staging / note['path']
                            output.parent.mkdir(exist_ok=True, mode=0o700)
                            output.write_bytes(exported_data)
                            output.chmod(0o600)
                        exported.setdefault("notes", []).append(note)
                if exported.get("withheld_previews"):
                    status_value["withheld_previews"] = exported["withheld_previews"]
                for proof in [] if withhold else turn.get('source_verification', []):
                    for label, image in proof.get('rendered', {}).items():
                        # Verifier edits are technical evidence, never solver design
                        # previews. Do not let modified pixels contaminate scoring.
                        if label in {'edited', 'edited-front'} or (proof.get('format') == 'blend' and label == 'source'):
                            continue
                        media = _copy_media(root, staging, image, max_file_bytes=max_file_bytes, total=total, max_total_bytes=max_total_bytes)
                        media.update(name='Independent capture / ' + image.get('label', label), kind='independent-source-capture')
                        exported['artifacts'].append(media)
                    status_value.setdefault('source_checks', []).append({
                        'format': proof.get('format', 'svg'),
                        'source_reopen_verified': proof.get('source_reopen_verified') is True,
                        'source_editability_verified': proof.get('source_editability_verified') is True,
                        'scope': proof.get('scope', proof.get('edit_scope')),
                        'playback': proof.get('playback'),
                        'generated_code_executed': proof.get('generated_code_executed') is True})
                status_data = json.dumps(status_value, sort_keys=True).encode()
                status_digest = hashlib.sha256(status_data).hexdigest()
                status_path = "metadata/" + status_digest + ".json"
                (staging / "metadata").mkdir(exist_ok=True)
                (staging / status_path).write_bytes(status_data)
                exported["status_evidence"] = {"path": status_path, "sha256": status_digest, "size": len(status_data), "kind": "delivery-status"}
                entry["turns"].append(exported)
            packet["entries"].append(entry)
            private["entries"][entry_id] = {"trial_id": trial_id, "arm": row["arm"], "case_id": row["case_id"], "repeat": row["repeat"]}
            groups.setdefault((row["case_id"], row["repeat"]), []).append(entry_id)
        for (case_id, repeat), entries in sorted(groups.items()):
            for left, right in itertools.combinations(entries, 2):
                if rng.getrandbits(1):
                    left, right = right, left
                packet["pairs"].append({"id": canonical_hash({"review": review_id, "entries": sorted([left, right])})[:16], "case_id": case_id, "repeat": repeat, "left": left, "right": right})
        for case_id, case in cases.items():
            for attachment in case.get("assets", case.get("attachments", [])):
                if attachment.get("visibility") == "private" and not allow_private:
                    packet["private_references_omitted"] = packet.get("private_references_omitted", 0) + 1
                    continue
                item = _copy_media(root, staging, attachment, max_file_bytes=max_file_bytes, total=total, max_total_bytes=max_total_bytes)
                item.update({"case_id": case_id, "name": attachment.get("id", "reference"), "id": attachment.get("id", "reference"), "license": attachment.get("license", "unspecified")})
                packet["references"].append(item)
        template = {"schema_version": 1, "review_id": review_id, "version": 1, "reviewer": {"id": "", "class": "human", "arm_map_seen": False}, "ratings": [], "pairs": []}
        for entry in packet["entries"]:
            for turn in entry["turns"]:
                for atom in entry["atoms"]:
                    if turn["turn"] in atom.get("active_turns", [item["turn"] for item in entry["turns"]]):
                        template["ratings"].append({"entry": entry["id"], "turn": turn["turn"], "atom": atom["id"], "score": "unverifiable", "evidence": [], "reason": ""})
        for pair in packet["pairs"]:
            template["pairs"].append({"pair": pair["id"], "outcome": "undetermined", "evidence": [], "reason": ""})
        _write_json(staging / "review.json", packet)
        _write_json(staging / "ratings-template.json", template)
        (staging / "index.html").write_text(render_review_html(packet, template), encoding="utf-8")
        private["packet_sha256"] = canonical_hash(packet)
        private_map_path.parent.mkdir(parents=True, exist_ok=True)
        private_map_path.parent.chmod(0o700)
        _write_json(private_map_path, private, private=True)
        if private_packet:
            staging.chmod(0o700)
        staging.rename(dest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        if private_map_path.exists():
            private_map_path.unlink()
        raise
    return packet


def _evidence_inventory(packet: dict) -> dict[str, str]:
    inventory = {item["path"]: item["sha256"] for item in packet.get("references", [])}
    for entry in packet.get("entries", []):
        for turn in entry.get("turns", []):
            for item in turn.get("artifacts", []) + ([turn["status_evidence"]] if "status_evidence" in turn else []):
                if item["path"] in inventory and inventory[item["path"]] != item["sha256"]:
                    raise ValueError("Conflicting evidence hashes")
                inventory[item["path"]] = item["sha256"]
            if packet.get('view') == 'notes-process-v2':
                if packet.get('notes_scope_version') != 2:
                    raise ValueError('Versioned text review condition is missing its scope identity')
                for note in turn.get('notes', []):
                    validate_declared_note(note, require_path=True)
                    if note['path'] in inventory and inventory[note['path']] != note['sha256']:
                        raise ValueError('Conflicting text evidence hashes')
                    inventory[note['path']] = note['sha256']
    return inventory


def validate_review(packet: dict, document: dict, *, media_root: str | Path | None = None) -> dict:
    """Validate complete applicable ratings and evidence against a blind packet."""
    if document.get("schema_version") != 1 or document.get("review_id") != packet.get("review_id"):
        raise ValueError("Review document does not match the packet")
    if type(document.get("version")) is not int or document["version"] < 1:
        raise ValueError("Review version must be a positive integer")
    reviewer = document.get("reviewer", {})
    if not isinstance(reviewer.get("id"), str) or not reviewer["id"].strip() or reviewer.get("class") not in {"human", "agent", "hybrid"} or type(reviewer.get("arm_map_seen")) is not bool:
        raise ValueError("Review requires reviewer identity, class and arm-map disclosure")
    expected = {(entry["id"], turn["turn"], atom["id"]) for entry in packet["entries"] for turn in entry["turns"] for atom in entry["atoms"] if turn["turn"] in atom.get("active_turns", [item["turn"] for item in entry["turns"]])}
    inventory = _evidence_inventory(packet)
    if packet.get('view') == 'notes-process-v2':
        note_total = 0
        for entry in packet.get('entries', []):
            for turn in entry.get('turns', []):
                for note in turn.get('notes', []):
                    note_total += len(validate_declared_note(note, media_root=media_root, require_path=True))
        if note_total > MAX_NOTE_TOTAL_BYTES:
            raise ValueError('Review declared text exceeds its aggregate byte limit')

    def evidence_check(row: dict) -> None:
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise ValueError("Every judgment requires an explicit reason")
        evidence = row.get("evidence", [])
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("Every judgment requires hash-linked evidence, including unknowns")
        for item in evidence:
            if not isinstance(item, dict) or inventory.get(item.get("path")) != item.get("sha256"):
                raise ValueError("Evidence is outside the packet hash allowlist")
            if media_root is not None:
                checked_file(Path(media_root), item["path"], expected_hash=item["sha256"])

    seen = set()
    unavailable = {(entry["id"], turn["turn"]) for entry in packet["entries"] for turn in entry["turns"] if turn.get("evidence_status") == "missing-result" or (packet.get('evidence_scope') == 'failed-turn-v1' and turn.get('evidence_status') == 'failed-no-model-output')}
    for row in document.get("ratings", []):
        key = (row.get("entry"), row.get("turn"), row.get("atom"))
        if key not in expected or key in seen:
            raise ValueError("Unknown, duplicate or inapplicable atom rating")
        score = row.get("score")
        if not ((type(score) is int and score in {0, 1, 2}) or score == "unverifiable"):
            raise ValueError("Use an ordinal 0/1/2 or unverifiable")
        if (row["entry"], row["turn"]) in unavailable and score != "unverifiable":
            raise ValueError("Missing sealed outcome evidence requires unverifiable, not an ordinal score")
        evidence_check(row)
        seen.add(key)
    if seen != expected:
        raise ValueError("Applicable atom ratings are incomplete")
    expected_pairs = {pair["id"] for pair in packet.get("pairs", [])}
    seen_pairs = set()
    pair_index = {pair["id"]: pair for pair in packet.get("pairs", [])}
    unavailable_entries = {entry["id"] for entry in packet["entries"] if entry.get("result_record") == "missing"}
    if packet.get('evidence_scope') == 'failed-turn-v1':
        unavailable_entries.update(entry['id'] for entry in packet['entries'] if any(turn.get('evidence_status') == 'failed-no-model-output' for turn in entry['turns']))
    for row in document.get("pairs", []):
        if row.get("pair") not in expected_pairs or row["pair"] in seen_pairs or row.get("outcome") not in OUTCOMES:
            raise ValueError("Invalid or duplicate paired outcome")
        pair = pair_index[row["pair"]]
        if {pair["left"], pair["right"]} & unavailable_entries and row["outcome"] != "undetermined":
            raise ValueError("A pair with missing sealed outcome evidence requires undetermined")
        evidence_check(row)
        seen_pairs.add(row["pair"])
    if seen_pairs != expected_pairs:
        raise ValueError("Paired outcomes are incomplete")
    return {"valid": True, "rated_atoms": len(seen), "paired_cases": len(seen_pairs), "automatic_quality_pass": None, "rating_sha256": canonical_hash(document)}


def freeze_review(packet: dict, document: dict, destination: str | Path, *, media_root: str | Path | None = None) -> dict:
    """Store a new immutable version; overwriting a frozen review is rejected."""
    summary = validate_review(packet, document, media_root=media_root)
    path = Path(destination) / packet["review_id"] / ("v" + str(document["version"]) + ".json")
    _write_json(path, {"schema_version": 1, "frozen": True, "sha256": summary["rating_sha256"], "review": document})
    path.chmod(0o444)
    return {**summary, "path": str(path)}

_REVIEW_STYLE = """body{font-family:system-ui,sans-serif;margin:1.5rem;color:#172b25;background:#f7f7f3}section{margin:2rem 0}.pair{display:flex;gap:1.2rem;align-items:flex-start;overflow:auto}.entry{flex:1;min-width:360px;background:white;padding:1rem;overflow:auto}img{max-width:100%;height:auto}.native img{max-width:none}figure{margin:1rem 0}figcaption{overflow-wrap:anywhere;font-size:.8rem}.rating{padding:.8rem;border-bottom:1px solid #d1d8d2}label{display:block;margin:.5rem 0}textarea{width:95%;min-height:4rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}button,select,input{padding:.4rem}details{margin:1rem 0}"""
_REVIEW_SCRIPT = r"""'use strict';
const packet=JSON.parse(document.getElementById('packet').textContent), template=JSON.parse(document.getElementById('template').textContent);
const state=structuredClone(template);
const entries=new Map(packet.entries.map(e=>[e.id,e]));
document.getElementById('native').addEventListener('change',e=>document.body.classList.toggle('native',e.target.checked));
function editor(row,isPair){const box=document.createElement('div');box.className='rating';const title=document.createElement('strong');title.textContent=isPair?'Pair '+row.pair:row.entry+' / turn '+row.turn+' / '+row.atom;box.append(title);const select=document.createElement('select');select.setAttribute('aria-label',title.textContent+' judgment');const unavailable=isPair?(()=>{const p=packet.pairs.find(p=>p.id===row.pair);return [p.left,p.right].some(id=>entries.get(id).result_record==='missing');})():entries.get(row.entry).turns.find(t=>t.turn===row.turn).evidence_status==='missing-result';const choices=unavailable?(isPair?['undetermined']:['unverifiable']):(isPair?['undetermined','win','tie','loss']:['unverifiable','0','1','2']);select.disabled=unavailable;for(const v of choices){const o=document.createElement('option');o.value=v;o.textContent=v;select.append(o);}select.addEventListener('change',()=>{row[isPair?'outcome':'score']=isPair||select.value==='unverifiable'?select.value:Number(select.value);});box.append(select);const reason=document.createElement('textarea');reason.setAttribute('aria-label',title.textContent+' reason');reason.placeholder='Describe observable evidence, or why it remains unknown.';reason.addEventListener('input',()=>row.reason=reason.value);box.append(reason);let evidence=[];if(isPair){const p=packet.pairs.find(p=>p.id===row.pair);for(const id of [p.left,p.right])for(const t of entries.get(id).turns)evidence.push(...t.artifacts,t.status_evidence);}else{const turn=entries.get(row.entry).turns.find(t=>t.turn===row.turn);evidence.push(...turn.artifacts,turn.status_evidence);}evidence.push(...packet.references);const seen=new Set();for(const item of evidence){if(!item||seen.has(item.path))continue;seen.add(item.path);const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';label.append(check,document.createTextNode((item.name||item.kind)+' / '+item.path));check.addEventListener('change',()=>{row.evidence=row.evidence.filter(e=>e.path!==item.path);if(check.checked)row.evidence.push({path:item.path,sha256:item.sha256});});box.append(label);}return box;}
for(const row of state.ratings)document.getElementById('rating-editors').append(editor(row,false));
for(const row of state.pairs)document.getElementById('pair-editors').append(editor(row,true));
document.getElementById('download').addEventListener('click',()=>{state.reviewer={id:document.getElementById('reviewer').value.trim(),class:document.getElementById('rater-class').value,arm_map_seen:document.getElementById('arm-map-seen').checked};state.version=Number(document.getElementById('review-version').value);if(!state.reviewer.id||!state.reviewer.class||!Number.isInteger(state.version)||state.version<1||[...state.ratings,...state.pairs].some(r=>!r.reason.trim()||!r.evidence.length)){document.getElementById('validation').textContent='Supply reviewer identity/class, a positive version and hash-linked evidence plus a reason for every judgment.';return;}const blob=new Blob([JSON.stringify(state,null,2)+'\n'],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='ratings-'+packet.review_id+'-v'+state.version+'.json';a.click();URL.revokeObjectURL(a.href);document.getElementById('validation').textContent='Downloaded draft. Import through skill-bench review to validate and freeze; this page does not grant a quality pass.';});
"""


def render_review_html(packet: dict, template: dict) -> str:
    """Render anonymous paired native-size inspection and evidence-linked drafts."""
    def payload(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    def image(item):
        return '<figure><img loading="lazy" src="' + html.escape(item["path"], quote=True) + '" alt="Hash-linked ' + html.escape(item.get("kind", "image"), quote=True) + '"><figcaption>' + html.escape(item.get("name", item.get("kind", "image"))) + '<br>' + html.escape(item["sha256"]) + '</figcaption></figure>'
    def entry_view(entry):
        body = '<article class="entry"><h3>Entry ' + html.escape(entry["id"]) + '</h3><p>Status: ' + html.escape(entry["status"]) + '</p>'
        for turn in entry["turns"]:
            body += '<h4>Turn ' + str(turn["turn"]) + '</h4>' + "".join(image(item) for item in turn["artifacts"])
            if packet.get('evidence_scope') == 'failed-turn-v1' and turn.get('evidence_status') != 'recorded':
                messages = {'failed-no-model-output': 'No model-output event was observed in the verified CLI stream. Persisted files and reopened images are withheld; applicable ratings must remain unverifiable.', 'partial-model-output': 'Partial model output was observed before this failed turn stopped. This snapshot may include earlier files; model activity does not prove that every file changed.', 'unknown-failed-output': 'Model-output scope could not be verified for this failed turn. Available files are retained without claiming a new final output.'}
                body += '<p>' + html.escape(messages.get(turn['evidence_status'], 'The execution result is missing.')) + '</p>'
            if turn.get("absence_reason"):
                body += '<p>' + html.escape(turn["absence_reason"]) + '</p><p>Evidence status: ' + html.escape(turn["evidence_status"]) + '</p>'
            for item in turn.get("withheld_previews", []):
                body += '<p>Preview withheld: ' + html.escape(item["name"]) + ' / ' + html.escape(item["sha256"]) + ' / ' + html.escape(item["withheld_reason"]) + '</p>'
            for note in turn.get("notes", []):
                label = 'Declared text output / process explanation: ' if packet.get('view') == 'notes-process-v2' else 'Process explanation: '
                body += '<details><summary>' + label + html.escape(note.get("name", "notes")) + ' (not a quality score)</summary><p>' + html.escape(note["sha256"]) + '</p><pre>' + html.escape(note["text"]) + '</pre></details>'
        body += '<details><summary>Input requirements and applicable rubric</summary><pre>' + html.escape(json.dumps({"prompts": entry.get("prompts", []), "requirements": entry.get("requirements", []), "atoms": entry["atoms"]}, indent=2, ensure_ascii=False)) + '</pre></details></article>'
        return body
    entries = {entry["id"]: entry for entry in packet["entries"]}
    shown = set()
    views = []
    for pair in packet["pairs"]:
        shown.update([pair["left"], pair["right"]])
        views.append('<section><h2>Pair ' + html.escape(pair["id"]) + ' / ' + html.escape(pair["case_id"]) + '</h2><p>Outcome is relative to the left entry. Compare changes across the visible turns.</p><div class="pair">' + entry_view(entries[pair["left"]]) + entry_view(entries[pair["right"]]) + '</div></section>')
    for entry in packet["entries"]:
        if entry["id"] not in shown:
            views.append('<section>' + entry_view(entry) + '</section>')
    script = _REVIEW_SCRIPT
    if packet.get('view') == 'notes-process-v2':
        script = script.replace('evidence.push(...t.artifacts,t.status_evidence)', 'evidence.push(...t.artifacts,...(t.notes||[]),t.status_evidence)').replace('evidence.push(...turn.artifacts,turn.status_evidence)', 'evidence.push(...turn.artifacts,...(turn.notes||[]),turn.status_evidence)')
    if packet.get('evidence_scope') == 'failed-turn-v1':
        script = script.replace("entries.get(id).result_record==='missing'", "(entries.get(id).result_record==='missing'||entries.get(id).turns.some(t=>t.evidence_status==='failed-no-model-output'))")
        script = script.replace("entries.get(row.entry).turns.find(t=>t.turn===row.turn).evidence_status==='missing-result'", "['missing-result','failed-no-model-output'].includes(entries.get(row.entry).turns.find(t=>t.turn===row.turn).evidence_status)")
    script_hash = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    style_hash = base64.b64encode(hashlib.sha256(_REVIEW_STYLE.encode()).digest()).decode()
    csp = "default-src 'none'; script-src 'sha256-" + script_hash + "'; style-src 'sha256-" + style_hash + "'; img-src 'self'; base-uri 'none'; form-action 'none'; connect-src 'none'"
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="' + html.escape(csp, quote=True) + '"><title>Anonymous skill review</title><style>' + _REVIEW_STYLE + '</style><body class="native"><h1>Anonymous independent review</h1><p>View: ' + html.escape(packet["view"]) + ' / Privacy: ' + html.escape(packet.get("privacy", "unknown")) + '</p><p>Review images first. Delivery success, model explanations and self-assessments do not establish quality. Use unverifiable when the available evidence cannot support the claim.</p><label><input id="native" type="checkbox" checked>Inspect images at original pixel size (scroll when needed)</label><section><h2>Actual input references</h2>' + "".join(image(item) for item in packet["references"]) + '</section>' + "".join(views) + '<section><h2>Independent judgments</h2><label>Reviewer ID <input id="reviewer" autocomplete="off"></label><label>Reviewer class <select id="rater-class"><option value="">Choose</option><option value="human">Human</option><option value="agent">Independent agent</option><option value="hybrid">Hybrid</option></select></label><label>Review version <input id="review-version" type="number" min="1" value="1"></label><label><input id="arm-map-seen" type="checkbox">I have seen the private arm mapping</label><div id="rating-editors"></div><h2>Case preferences</h2><div id="pair-editors"></div><button id="download" type="button">Download review draft</button><p id="validation"></p></section><script type="application/json" id="packet">' + payload(packet) + '</script><script type="application/json" id="template">' + payload(template) + '</script><script>' + script + '</script></body></html>'
