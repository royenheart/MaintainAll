"""Import a completed v1 pilot as historical evidence, without re-execution.

The importer preserves v1 prompts/rubrics and raw records, copies verified
primary snapshots, and never imports old scores into a new anonymous review.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import time

from .review import canonical_hash, checked_file
from .store import private_directory, write_immutable

ARM_MAP = {'old': 'previous', 'new': 'candidate'}
TOKEN_FIELDS = ('input_tokens', 'cached_input_tokens', 'uncached_input_tokens', 'output_tokens')
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_IMPORT_BYTES = 256 * 1024 * 1024


def import_legacy(source: Path, output: Path) -> dict:
    """Adapt v1 multi-reference runs to the current review/report evidence shape.

    Only recorded normalized initial/delta usage is eligible for efficiency
    reporting. Cumulative raw usage is retained privately and never summed.
    Missing historical properties are explicit unknowns, not reconstructed facts.
    """
    src = Path(source)
    if Path(output).resolve().is_relative_to(src.resolve()):
        raise ValueError('Historical import output must remain outside its source')
    _, original_bytes = checked_file(src, 'manifest.json', max_bytes=MAX_FILE_BYTES)
    original = json.loads(original_bytes)
    if original.get('schema_version') != 1 or not isinstance(original.get('cards'), list) or not isinstance(original.get('skills'), dict):
        raise ValueError('Expected a v1 complex-pilot manifest with cards and skills')
    cards = original['cards']
    if not cards or len({c['id'] for c in cards}) != len(cards):
        raise ValueError('Missing or duplicate historical cards')
    if set(original['skills']) != set(ARM_MAP):
        raise ValueError('Only explicit old/new historical arms are supported')
    root = private_directory(output, must_be_new=True)
    copied = []
    total = [0]

    def copy_evidence(relative: str, target_relative: str, expected_hash=None, expected_size=None):
        _, data = checked_file(src, relative, expected_hash=expected_hash, expected_size=expected_size, max_bytes=MAX_FILE_BYTES)
        total[0] += len(data)
        if total[0] > MAX_IMPORT_BYTES:
            raise ValueError('Legacy import exceeds the aggregate byte limit')
        relative_path = PurePosixPath(target_relative)
        if relative_path.is_absolute() or '..' in relative_path.parts or '\\' in target_relative:
            raise ValueError('Unsafe imported evidence path')
        target = root / target_relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.exists() or target.is_symlink():
            raise ValueError('Imported evidence cannot be replaced')
        with target.open('xb') as handle:
            handle.write(data)
        target.chmod(0o400)
        record = {'source': relative, 'snapshot': target_relative, 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
        copied.append(record)
        return record

    try:
        copy_evidence('manifest.json', 'legacy/source-manifest.json')
        for optional in ('summary.json', 'mechanical-summary.json', 'mechanical-check.json', 'preflight-old.json', 'preflight-new.json'):
            if (src / optional).exists():
                copy_evidence(optional, 'legacy/' + optional)
        cases, schedule, results, arms, case_hashes = [], [], [], [], {}
        for card in cards:
            rounds = card.get('rounds', [])
            if not rounds:
                raise ValueError('Historical card has no rounds')
            case = {'schema_version': 1, 'id': card['id'], 'version': card.get('version', 'unknown'), 'family': 'legacy_v1', 'split': 'development', 'turns': [{'id': f't{i + 1}', 'prompt': r['prompt'], 'attachments': r.get('attachments', []), 'artifacts': r.get('required_artifacts', [])} for i, r in enumerate(rounds)], 'assets': [], 'requirements': [], 'atoms': [], 'legacy': True, 'provenance': {'origin': 'historical v1 complex pilot', 'requirement_quote_alignment': 'unknown; not present in v1 records', 'rubric_version': 'original v1; not interchangeable with v2 corrected applicability', 'quality_imported': False}}
            for atom in card.get('rubric', []):
                case['atoms'].append({**copy.deepcopy(atom), 'dimension': atom.get('dimension', 'unknown'), 'active_turns': atom.get('applicable_turns', list(range(1, len(rounds) + 1))), 'requirement_ids': [], 'depends_on': [], 'legacy_requirement_alignment': 'unknown'})
            for attachment in card.get('attachments', []):
                staged = attachment.get('staged_path')
                if not staged:
                    raise ValueError('Historical attachment has no recorded staged path')
                relative = f'old/{card["id"]}/round1/artifacts/{staged}'
                if not (src / relative).exists():
                    # The v1 capture excludes mounted read-only inputs/skills.
                    # Its private workspace is an eligible source only when its
                    # bytes still match the originally recorded hash.
                    relative = f'old/{card["id"]}/workspace/{staged}'
                target = f'assets/{card["id"]}/{Path(staged).name}'
                ref = copy_evidence(relative, target, attachment['sha256'], attachment.get('bytes'))
                license_ = attachment.get('license', 'unknown')
                case['assets'].append({**copy.deepcopy(attachment), 'path': target, 'snapshot': target, 'size': ref['size'], 'visibility': 'public' if license_.lower().startswith('cc0') else 'private', 'legacy_evidence_source': ref['source']})
            if any(a['visibility'] == 'private' for a in case['assets']):
                case['visibility'] = 'private'
            cases.append(case)
            case_hashes[case['id']] = {'frozen_sha256': canonical_hash(case), 'rubric_sha256': canonical_hash({'requirements': [], 'atoms': case['atoms']}), 'source_sha256': original.get('cards_sha256', {}).get(case['id'], 'unknown')}
            for legacy_arm, mapped_arm in ARM_MAP.items():
                trial_id = f'{card["id"]}--r001--{mapped_arm}'
                schedule.append({'trial_id': trial_id, 'case_id': card['id'], 'arm': mapped_arm, 'repeat': 1})
                turns, statuses = [], []
                for turn_no, round_ in enumerate(rounds, 1):
                    prefix = f'{legacy_arm}/{card["id"]}/round{turn_no}'
                    raw_ref = copy_evidence(prefix + '/result.json', f'legacy/{prefix}/result.json')
                    raw = json.loads((root / raw_ref['snapshot']).read_text())
                    if (raw.get('arm'), raw.get('task'), raw.get('turn')) != (legacy_arm, card['id'], turn_no):
                        raise ValueError('Historical result identity disagrees with its location')
                    status = raw.get('status', 'unknown')
                    if status not in ('completed', 'failed', 'interrupted', 'unsupported'):
                        raise ValueError('Historical result status cannot be represented safely')
                    statuses.append(status)
                    declared = {a['path']: a for a in round_.get('required_artifacts', [])}
                    inventory = {a['path']: a for a in raw.get('outcome', {}).get('artifacts', [])}
                    artifacts = []
                    for name, artifact in declared.items():
                        evidence = inventory.get(name)
                        # A failed original delivery may lack a file. Preserve that
                        # absence instead of pretending it became successful.
                        path = src / prefix / 'artifacts' / name
                        if not path.exists():
                            if evidence and evidence.get('passed') is True:
                                raise ValueError('A historically successful snapshot is missing')
                            continue
                        ref = copy_evidence(prefix + '/artifacts/' + name, f'trials/{trial_id}/turn-{turn_no}/artifacts/{name}', evidence.get('sha256') if evidence else None, evidence.get('bytes') if evidence else None)
                        artifacts.append({'path': name, 'snapshot': f'turn-{turn_no}/artifacts/{name}', 'sha256': ref['sha256'], 'size': ref['size'], 'kind': artifact['kind'], 'legacy_hash_verified': bool(evidence and evidence.get('sha256'))})
                    if (src / prefix / 'artifacts/notes.md').exists():
                        ref = copy_evidence(prefix + '/artifacts/notes.md', f'trials/{trial_id}/turn-{turn_no}/artifacts/notes.md')
                        artifacts.append({'path': 'notes.md', 'snapshot': f'turn-{turn_no}/artifacts/notes.md', 'sha256': ref['sha256'], 'size': ref['size'], 'kind': 'notes', 'review_safe': False})
                    trace_refs = []
                    for filename in ('events.jsonl', 'stderr.log', 'final.txt'):
                        if (src / prefix / filename).exists():
                            trace_refs.append(copy_evidence(prefix + '/' + filename, f'legacy/{prefix}/{filename}'))
                    recorded_usage = raw.get('usage', {})
                    usage_status = recorded_usage.get('usage_status', 'unknown')
                    eligible = usage_status in ('initial_thread_total', 'thread_total_delta')
                    usage = {key: recorded_usage.get(key) if eligible else None for key in TOKEN_FIELDS}
                    outcome = raw.get('outcome', {})
                    turns.append({'turn': turn_no, 'status': status, 'seconds': raw.get('elapsed_seconds'), 'usage': usage, 'legacy_usage_status': usage_status, 'thread_id': raw.get('thread_id'), 'delivery': {'delivery_pass': outcome.get('delivery_pass'), 'provenance': 'recorded historical delivery; not rerun by this importer'}, 'source_editability_verified': outcome.get('source_editability_verified') if type(outcome.get('source_editability_verified')) is bool else None, 'quality_status': 'unassessed', 'quality_score': None, 'artifacts': artifacts, 'legacy_record': raw_ref, 'legacy_traces': trace_refs, 'inputs_unchanged': raw.get('inputs_unchanged'), 'image_evidence': copy.deepcopy(raw.get('image_evidence', {})), 'preservation': {'passed': None, 'provenance': 'unknown; no new preservation judgment is imported'}})
                aggregate_status = 'completed' if all(s == 'completed' for s in statuses) else next(s for s in statuses if s != 'completed')
                result = {'schema_version': 1, 'trial_id': trial_id, 'case_id': card['id'], 'arm': mapped_arm, 'repeat': 1, 'status': aggregate_status, 'turns': turns, 'backend': {'id': 'legacy-v1-local-codex', 'fingerprint': 'unknown'}, 'quality_status': 'unassessed', 'legacy': True, 'import_mode': 'historical_v1'}
                result_seal = write_immutable(root / 'trials' / trial_id / 'result.json', result)
                write_immutable(root / 'trials' / trial_id / 'result-seal.json', {'sha256': result_seal})
                (root / 'trials' / trial_id / 'result-seal.json').chmod(0o400)
                (root / 'trials' / trial_id / 'result.json').chmod(0o400)
                results.append(result)
        for legacy_arm, mapped_arm in ARM_MAP.items():
            skill = original['skills'][legacy_arm]
            arm = {'id': mapped_arm, 'legacy_arm': legacy_arm, 'skill_hash': skill.get('sha256', 'unknown'), 'files': copy.deepcopy(skill.get('files', {})), 'logical_files': len(skill.get('files', {})), 'skill_snapshot': None}
            # Import only an actual captured skill, never the mutable host path
            # recorded in the old manifest.
            if arm['files']:
                card_id = cards[0]['id']
                for name, expected in arm['files'].items():
                    relative = f'{legacy_arm}/{card_id}/round1/artifacts/skill/{name}'
                    if not (src / relative).exists():
                        relative = f'{legacy_arm}/{card_id}/workspace/skill/{name}'
                    copy_evidence(relative, f'skills/{mapped_arm}/{name}', expected)
                arm['skill_snapshot'] = f'skills/{mapped_arm}'
            arms.append(arm)
        manifest = {'schema_version': 1, 'id': 'legacy-' + src.name, 'legacy': True, 'import_mode': 'historical_v1', 'mode': 'legacy_import', 'imported_epoch': time.time(), 'legacy_source_state': original.get('state', 'unknown'), 'source_manifest_sha256': hashlib.sha256(original_bytes).hexdigest(), 'model': original.get('model', 'unknown'), 'effort': original.get('effort', 'unknown'), 'codex_version': original.get('codex_version', 'unknown'), 'backend': 'legacy-v1-local-codex', 'backend_fingerprint': 'unknown', 'cases': cases, 'case_hashes': case_hashes, 'arms': arms, 'schedule': schedule, 'schedule_is_adapter_enumeration_not_execution_order': True, 'original_execution_order': 'unknown', 'repeats': 1, 'order_seed': None, 'provider_sampling_seed': original.get('seed'), 'provider_snapshot': original.get('provider_snapshot'), 'currency_cost': original.get('currency_cost'), 'suite_id': 'legacy-adapted-v1-card-set', 'suite_sha256': canonical_hash(original['cards']), 'suite_hash_kind': 'canonical-v1-cards; not a source suite-file digest', 'suite_fingerprint': canonical_hash(original['cards']), 'runtime': {'backend': 'legacy-v1-local-codex', 'adapter_sha256': 'unknown', 'renderer': original.get('renderer', 'unknown'), 'renderer_identity': 'unknown', 'model': original.get('model', 'unknown'), 'effort': original.get('effort', 'unknown'), 'codex_version': original.get('codex_version', 'unknown')}, 'backend_config': {}, 'limits': {'max_calls': original.get('max_cli_calls'), 'planned_calls': sum(len(c['turns']) for c in cases) * len(arms), 'wall_seconds': original.get('max_wall_seconds'), 'turn_seconds': next(iter({c.get('limits', {}).get('timeout_seconds') for c in cards})) if len({c.get('limits', {}).get('timeout_seconds') for c in cards}) == 1 else None}, 'quality_status': 'unassessed', 'quality_scores_imported': False, 'limitations': ['Historical v1 rubric and unknown quote alignment remain unchanged; not comparable to corrected v2 scores.', 'Old ratings, if any, are not imported as new blinded or independent review.', 'Only recorded normalized initial/delta usage is reportable; raw cumulative usage is preserved privately and never aggregated.', 'Backend fingerprint, original execution order and absent historical properties are unknown.', 'Copied evidence scope is original records/traces, declared primary artifacts, notes, references and captured logical skills; other workspace files remain in the original source.']}
        manifest['fingerprint'] = canonical_hash({k: v for k, v in manifest.items() if k != 'imported_epoch'})
        write_immutable(root / 'legacy/inventory.json', {'schema_version': 1, 'records': copied, 'bytes': total[0]})
        manifest_seal = write_immutable(root / 'manifest.json', manifest)
        write_immutable(root / 'manifest-seal.json', {'sha256': manifest_seal})
        (root / 'manifest-seal.json').chmod(0o400)
        (root / 'manifest.json').chmod(0o400)
        (root / 'legacy/inventory.json').chmod(0o400)
        return manifest
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
