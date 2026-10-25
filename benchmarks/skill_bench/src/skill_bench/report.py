"""Sanitized, filterable reports that separate cohorts and rating dimensions."""
from __future__ import annotations

import base64
from collections import Counter, defaultdict
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from .review import blind_entry_id, canonical_hash, checked_file, execution_state, missing_trial_observation, preview_validation, validate_packet_mapping, validate_review, MEDIA_SUFFIXES

TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens")
TOOL_FIELDS = ("tool_commands", "nonzero_tool_commands", "cli_warning_items", "cli_error_items")
VERIFIER_FIELDS = ("sha256", "source_verifier_sha256", "source_runtime_fingerprint", "reopen_sources")
_STATUSES = {"completed", "failed", "interrupted", "unsupported"}


def _case_context(case: dict) -> dict:
    """Copy only declared public task text; derived private outputs stay private."""
    private = case.get("visibility") == "private" or any(asset.get("visibility") == "private" for asset in case.get("assets", case.get("attachments", [])))
    context = {"case_id": case["id"], "case_fingerprint": canonical_hash(case), "visibility": "private" if private else "public"}
    if private:
        return context
    if isinstance(case.get("title"), str):
        context["title"] = case["title"]
    context["turns"] = []
    for number, turn in enumerate(case.get("turns", []), 1):
        item = {"turn": number}
        if isinstance(turn.get("prompt"), str):
            item["prompt"] = turn["prompt"]
        item["attachments"] = [value for value in turn.get("attachments", []) if isinstance(value, str)]
        item["artifacts"] = [{key: declaration[key] for key in ("path", "kind", "format") if isinstance(declaration.get(key), str)} for declaration in turn.get("artifacts", [])]
        context["turns"].append(item)
    context["requirements"] = [{key: item[key] for key in ("id", "quote", "turn") if key in item and (isinstance(item[key], str) if key != "turn" else type(item[key]) is int)} for item in case.get("requirements", [])]
    context["atoms"] = []
    for atom in case.get("atoms", []):
        item = {key: atom[key] for key in ("id", "dimension", "criterion") if isinstance(atom.get(key), str)}
        item["active_turns"] = [value for value in atom.get("active_turns", []) if type(value) is int and value > 0]
        item["requirement_ids"] = [value for value in atom.get("requirement_ids", []) if isinstance(value, str)]
        item["anchors"] = {key: value for key, value in atom.get("anchors", {}).items() if key in {"0", "1", "2"} and isinstance(value, str)}
        evidence = atom.get("evidence", {})
        item["required_artifacts"] = [value for value in evidence.get("required_artifacts", []) if isinstance(value, str)]
        context["atoms"].append(item)
    _assert_public(context)
    return context


def _experiment_metadata(manifest: dict) -> dict:
    """Expose verified commit identity when recorded, never infer it from dates."""
    backend = manifest.get("backend", "unknown")
    item = {"id": manifest["id"], "fingerprint": manifest.get("fingerprint", "unknown"), "model": manifest.get("model", "unknown"), "effort": manifest.get("effort", "unknown"), "backend": backend.get("id", "unknown") if isinstance(backend, dict) else backend, "invocation_mode": manifest.get("mode", "unknown"), "arms": [{"id": arm if isinstance(arm, str) else arm["id"], "skill_hash": arm.get("skill_hash") if isinstance(arm, dict) else None} for arm in manifest.get("arms", [])]}
    provenance = {}
    for key, value in manifest.get("commit_provenance", {}).items():
        if key in {"candidate_sha", "previous_sha", "trusted_sha"}:
            valid = isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value)
        elif key == "tracking_key":
            valid = isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
        elif key in {"source_run_id", "source_run_attempt"}:
            valid = type(value) is int and value > 0
        elif key == "protocol_id":
            valid = isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value)
        elif key == "source":
            valid = value == "local-manual"
        elif key in {"candidate_committed_epoch", "previous_committed_epoch"}:
            valid = type(value) is int and value >= 0
        elif key == "candidate_parents":
            valid = isinstance(value, list) and len(value) <= 32 and all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{40}", v) for v in value)
        else:
            continue
        if not valid:
            raise ValueError("Invalid public commit provenance field: " + key)
        provenance[key] = value
    item["commit_provenance"] = provenance
    return item


def _number(value: Any) -> int | float | None:
    return value if type(value) in {int, float} and math.isfinite(value) and value >= 0 else None


def _count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _total(turns: list[dict], field: str, *, usage: bool = False, count: bool = False) -> int | float | None:
    measure = _count if count else _number
    values = [measure(turn.get("usage", {}).get(field) if usage else turn.get(field)) for turn in turns]
    return sum(values) if values and all(value is not None for value in values) else None


def _cohort(manifest: dict, row: dict, case: dict, arm: dict, result: dict, judge: dict | None = None) -> dict:
    backend = result.get("backend", manifest.get("backend", "unknown"))
    if isinstance(backend, dict):
        backend_id, backend_fingerprint = backend.get("id", "unknown"), backend.get("fingerprint", "unknown")
    else:
        backend_id, backend_fingerprint = backend, manifest.get("backend_fingerprint", "unknown")
    verifier = manifest.get("mechanical_verifier", {"sha256": "unrecorded-initial:" + manifest["id"], "source_verifier_sha256": "unknown", "reopen_sources": False})
    verifier_identity = {key: verifier.get(key, "unknown") for key in VERIFIER_FIELDS}
    runtime = manifest.get("runtime")
    runtime_fingerprint = canonical_hash(runtime) if isinstance(runtime, dict) and runtime else manifest.get("fingerprint") or "unknown-by-experiment:" + manifest["id"]
    identity = {"generation_runtime_fingerprint": runtime_fingerprint, "invocation_mode": manifest.get("mode", "unknown"), "execution_policy_fingerprint": canonical_hash(manifest["limits"]) if isinstance(manifest.get("limits"), dict) else "unrecorded:" + manifest["id"], "mechanical_verifier": verifier_identity, "skill": row["arm"], "skill_hash": arm.get("skill_hash", "unknown"), "model": manifest.get("model", "unknown"), "effort": manifest.get("effort", "unknown"), "backend": backend_id, "backend_fingerprint": backend_fingerprint, "case_id": case["id"], "case_version": case.get("version", "unknown"), "case_fingerprint": canonical_hash(case), "rubric_fingerprint": canonical_hash({"requirements": case.get("requirements", []), "atoms": case.get("atoms", [])}), "suite_fingerprint": manifest.get("suite_sha256", manifest.get("suite_fingerprint", manifest.get("suite", {}).get("fingerprint", "unknown") if isinstance(manifest.get("suite"), dict) else "unknown")), "judge": judge or {"class": "unassessed", "id": "none", "version": 0}}
    identity["trial_order_seed"] = manifest.get("order_seed", "unrecorded:" + manifest["id"])
    return {"id": canonical_hash(identity)[:24], **identity}


def build_report(manifest: dict, results: list[dict], reviews: list[dict] | None = None, *, execution_events: list[dict] | None = None, skill_root: str | Path | None = None) -> dict:
    """Build allowlisted report data; raw logs and model self-scores are ignored.

    Review bundles contain ``packet``, validated ``document`` and the private
    ``arm_map``. Entry-to-trial mapping is consumed but never copied publicly.
    Each cohort includes task/rubric/backend/judge fingerprints, preventing a
    changed measurement or task from sharing an apparent trend series.
    ``execution_events`` must come from ``store.read_events``. A closed ledger
    permits scheduled missing records, represented as evidence gaps only.
    """
    case_map = {case["id"]: case for case in manifest.get("cases", [])}
    arm_map = {arm if isinstance(arm, str) else arm["id"]: {"id": arm} if isinstance(arm, str) else arm for arm in manifest.get("arms", [])}
    schedule = {row["trial_id"]: row for row in manifest.get("schedule", [])}
    result_map = {result["trial_id"]: result for result in results}
    if len(result_map) != len(results) or len(schedule) != len(manifest.get("schedule", [])):
        raise ValueError("Duplicate trial IDs in report inputs")
    if set(result_map) - set(schedule):
        raise ValueError("Results contain trials outside the frozen schedule")
    terminal = execution_state(execution_events)
    if set(schedule) - set(result_map) and not terminal["closed"]:
        raise ValueError("Missing results require a closed execution ledger before reporting")
    report = {"schema_version": 1, "kind": "skill-benchmark-report", "mechanical_verifier": {key: manifest.get("mechanical_verifier", {}).get(key, "unknown") for key in (*VERIFIER_FIELDS, "regrade_id")}, "experiment": manifest["id"], "fingerprint": manifest.get("fingerprint", canonical_hash(manifest)), "cohorts": [], "trials": [], "ratings": [], "pairs": [], "dimensions": [], "media": [], "automatic_quality_pass": None, "aggregate_aesthetic_score": None, "limitations": ["Cases, repeats, turn observations and atom observations are reported separately.", "Ordinal ratings are not an aesthetic total and unknown is not zero.", "Cohorts with changed tasks, rubric, model, skill, backend or judge must not share one trend series.", "Mechanical delivery and preserved bytes do not establish visual quality or source editability.", "No causal skill improvement follows from one case or one fixed-order repeat.", "Source program rebuild, rigging, motion and physical material properties require their declared backend evidence."]}
    report.update(current_experiment=manifest["id"], experiments=[_experiment_metadata(manifest)], case_contexts=[_case_context(case) for case in case_map.values()])
    if skill_root is not None:
        from .changes import skill_changes
        change = skill_changes(skill_root, manifest)
        if change is not None:
            report['experiments'][0]['skill_changes'] = change
    cohort_map = {}
    trial_index = {}
    for trial_id, row in schedule.items():
        if row["case_id"] not in case_map or row["arm"] not in arm_map:
            raise ValueError("Schedule references an unknown case or arm")
        case, arm = case_map[row["case_id"]], arm_map[row["arm"]]
        recorded = trial_id in result_map
        result = result_map[trial_id] if recorded else missing_trial_observation(case, trial_id, terminal)
        status = result.get("status")
        if recorded and status not in _STATUSES:
            raise ValueError("Unknown trial status")
        turns = result.get("turns", [])
        cohort = _cohort(manifest, row, case, arm, result)
        cohort_map[cohort["id"]] = cohort
        trial = {"id": trial_id, "case_id": row["case_id"], "case_version": case.get("version", "unknown"), "arm": row["arm"], "repeat": row["repeat"], "model": cohort["model"], "effort": cohort["effort"], "backend": cohort["backend"], "skill_hash": cohort["skill_hash"], "cohort_id": cohort["id"], "status": status, "quality_status": "unassessed", "seconds": _total(turns, "seconds"), "usage": {**{field: _total(turns, field, usage=True) for field in TOKEN_FIELDS}, **{field: _total(turns, field, usage=True, count=True) for field in TOOL_FIELDS}}, "turns": [], "privacy": "private" if case.get("visibility") == "private" or any(asset.get("visibility") == "private" for asset in case.get("assets", case.get("attachments", []))) else "public"}
        trial.update(result_record="present" if recorded else "missing", planned_turns=len(case.get("turns", [])), recorded_turns=len(turns) if recorded else 0)
        if not recorded:
            trial["absence_reason"] = result["absence_reason"]
        for turn in turns:
            delivery = turn.get("delivery", {})
            passed = delivery.get("passed", delivery.get("delivery_pass")) if isinstance(delivery, dict) else None
            preserved = turn.get("preservation", {})
            turn_item = {"turn": turn["turn"], "status": turn.get("status", status), "delivery_pass": passed if type(passed) is bool else None, "preservation_pass": preserved.get("passed") if isinstance(preserved, dict) and type(preserved.get("passed")) is bool else None, "source_editability_verified": turn.get("source_editability_verified", delivery.get("source_editability_verified")) if type(turn.get("source_editability_verified", delivery.get("source_editability_verified"))) is bool else None, "seconds": _number(turn.get("seconds")), "usage": {**{field: _number(turn.get("usage", {}).get(field)) for field in TOKEN_FIELDS}, **{field: _count(turn.get("usage", {}).get(field)) for field in TOOL_FIELDS}}}
            allowed_sources = {item["sha256"]: item["path"] for item in turn.get("artifacts", []) if item.get("kind") == "editable" and any(declaration["path"] == item["path"] for specification in case.get("turns", []) for declaration in specification.get("artifacts", []))}
            turn_item["source_proofs"] = []
            turn_item["evidence_status"] = "recorded" if recorded else "missing-result"
            if not recorded:
                turn_item["absence_reason"] = result["absence_reason"]
            for proof in turn.get("source_verification", []):
                if proof.get("source_sha256") not in allowed_sources:
                    raise ValueError("Source proof does not correspond to a declared editable artifact")
                source_name = allowed_sources[proof["source_sha256"]]
                native = proof.get('format') in {'html', 'blend'}
                scope = proof.get('scope', 'bounded visual source verification') if native else "one existing SVG fill attribute only; no rigging, layout-parameter or whole-project readiness claim"
                turn_item["source_proofs"].append({"name": source_name, "source_sha256": proof["source_sha256"], "source_reopen_verified": proof.get("source_reopen_verified") is True,
                                                   "one_fill_edit_verified": proof.get("source_editability_verified") is True if not native else False,
                                                   "bounded_native_edit_verified": proof.get("source_editability_verified") is True if proof.get('format') == 'blend' else False,
                                                   "format": proof.get('format', 'svg'), "scope": scope,
                                                   "playback": proof.get('playback')})
                if trial["privacy"] == "public":
                    for label, image in proof.get("rendered", {}).items():
                        if label not in {"source", "edited"} and not (native and re.fullmatch(r'[a-zA-Z0-9_.-]{1,96}', label)):
                            raise ValueError("Unsupported source proof render type")
                        report["media"].append({"trial_id": trial_id, "turn": turn["turn"], "name": source_name + (' / ' + label if native else ''), "path": image["path"], "sha256": image["sha256"], "size": image["size"], "kind": "verifier-edit" if native and label in {"edited", "edited-front"} else "independent-capture" if native else "source-rebuild" if label == "source" else "one-fill-edit", "root": "run", "privacy": "public", "scope": scope})
            trial["turns"].append(turn_item)
            if trial["privacy"] == "public":
                declared = {item["path"] for item in case.get("turns", [])[turn["turn"] - 1].get("artifacts", [])} if 1 <= turn["turn"] <= len(case.get("turns", [])) else set()
                for artifact in turn.get("artifacts", []):
                    if Path(artifact.get("path", "")).suffix.lower() in MEDIA_SUFFIXES:
                        report["media"].append({"trial_id": trial_id, "turn": turn["turn"], "name": artifact["path"] if artifact.get("path") in declared else "additional-preview", "path": artifact["snapshot"], "sha256": artifact["sha256"], "size": artifact["size"], "kind": "preview", "root": "trial", "privacy": "public"})
        report["trials"].append(trial)
        trial_index[trial_id] = trial
        if trial["privacy"] == "public":
            for asset in case.get("assets", case.get("attachments", [])):
                if asset.get("visibility") != "private" and Path(asset.get("snapshot", asset.get("path", ""))).suffix.lower() in MEDIA_SUFFIXES:
                    item = {"case_id": case["id"], "name": asset["id"], "path": asset.get("snapshot", asset["path"]), "sha256": asset["sha256"], "size": asset.get("size"), "root": "run", "privacy": "public", "kind": "reference", "license": asset.get("license", "unspecified")}
                    if item not in report["media"]:
                        report["media"].append(item)
    observations = defaultdict(Counter)
    for bundle in reviews or []:
        packet, document, mapping = bundle["packet"], bundle["document"], bundle["arm_map"]
        validate_packet_mapping(packet, mapping)
        validate_review(packet, document)
        expected_revision = manifest.get('mechanical_verifier', {}).get('regrade_id')
        if packet.get('source_revision') != expected_revision:
            raise ValueError('Review evidence source revision differs from the selected report; export and review the selected revision')
        if mapping.get("review_id") != packet["review_id"]:
            raise ValueError("Review mapping does not match the packet")
        reviewer = document["reviewer"]
        judge = {"class": reviewer["class"], "id": canonical_hash(reviewer["id"])[:16], "version": document["version"], "arm_map_seen": reviewer["arm_map_seen"], "view": packet["view"]}
        if 'source_revision' in packet:
            # The exact record ID binds provenance, but each run naturally has
            # a different ID. Comparable conditions use verifier/runtime and
            # the evidence scope, keeping matching commit histories possible.
            judge['evidence_scope'] = 'independent-source-captures' if packet['source_revision'] else 'original-solver-evidence'
        if 'evidence_scope' in packet:
            if packet['evidence_scope'] != 'failed-turn-v1':
                raise ValueError('Unsupported failed-turn review evidence scope')
            judge['failed_turn_evidence_scope'] = packet['evidence_scope']
        entry_map = mapping["entries"]
        packet_entries = {entry["id"]: entry for entry in packet["entries"]}
        for rating in document["ratings"]:
            trial_id = entry_map[rating["entry"]]["trial_id"]
            if trial_id not in trial_index:
                raise ValueError("Review maps to an unknown trial")
            if blind_entry_id(packet["review_id"], trial_id, mapping.get("private_key")) != rating["entry"]:
                raise ValueError("Private review mapping does not match its anonymous entry fingerprint")
            mapped = entry_map[rating["entry"]]
            planned = schedule[trial_id]
            if any(mapped.get(key) != planned.get(key) for key in ("case_id", "arm", "repeat")):
                raise ValueError("Review mapping disagrees with the frozen schedule")
            row, trial = schedule[trial_id], trial_index[trial_id]
            case, arm = case_map[row["case_id"]], arm_map[row["arm"]]
            cohort = _cohort(manifest, row, case, arm, result_map.get(trial_id, {}), judge)
            cohort_map[cohort["id"]] = cohort
            atom = next((item for item in case["atoms"] if item["id"] == rating["atom"]), None)
            if atom is None:
                raise ValueError("Review atom is not part of the frozen case")
            public_rating = {"trial_id": trial_id, "case_id": row["case_id"], "arm": row["arm"], "repeat": row["repeat"], "turn": rating["turn"], "atom": rating["atom"], "dimension": atom.get("dimension", "unspecified"), "score": rating["score"], "cohort_id": cohort["id"], "judge": judge, "review_id": packet["review_id"], "review_version": document["version"], "evidence": rating["evidence"] if trial["privacy"] == "public" else [], "reason": rating["reason"] if trial["privacy"] == "public" else "Private review reason withheld from public report.", "privacy": trial["privacy"]}
            if 'source_revision' in packet:
                public_rating['source_revision'] = packet['source_revision']
            report["ratings"].append(public_rating)
            observations[(cohort["id"], public_rating["dimension"])][str(rating["score"])] += 1
            trial["quality_status"] = "exploratory_independent_review"
        pairs = {pair["id"]: pair for pair in packet["pairs"]}
        for rating in document["pairs"]:
            pair = pairs[rating["pair"]]
            left = entry_map[pair["left"]]
            right = entry_map[pair["right"]]
            if left["case_id"] != right["case_id"] or left["repeat"] != right["repeat"]:
                raise ValueError("Paired outcome crosses cases or repeats")
            if any(blind_entry_id(packet["review_id"], item["trial_id"], mapping.get("private_key")) != pair[side] for side, item in (("left", left), ("right", right))):
                raise ValueError("Paired review entry fingerprint is inconsistent")
            if any(schedule[item["trial_id"]][key] != item[key] for item in (left, right) for key in ("arm", "case_id", "repeat")):
                raise ValueError("Paired review mapping disagrees with the schedule")
            private = trial_index[left["trial_id"]]["privacy"] == "private" or trial_index[right["trial_id"]]["privacy"] == "private"
            paired_case = case_map[pair["case_id"]]
            rubric_fingerprint = canonical_hash({"requirements": paired_case.get("requirements", []), "atoms": paired_case.get("atoms", [])})
            paired_cohorts = {}
            for side, entry in (("left", left), ("right", right)):
                cohort = _cohort(manifest, schedule[entry["trial_id"]], paired_case, arm_map[entry["arm"]], result_map.get(entry["trial_id"], {}), judge)
                cohort_map[cohort["id"]] = cohort
                paired_cohorts[side + "_cohort_id"] = cohort["id"]
            report["pairs"].append({"case_id": pair["case_id"], "case_fingerprint": canonical_hash(paired_case), "left_trial_id": left["trial_id"], "right_trial_id": right["trial_id"], **paired_cohorts, "rubric_fingerprint": rubric_fingerprint, "repeat": pair["repeat"], "model": manifest.get("model", "unknown"), "effort": manifest.get("effort", "unknown"), "backend": trial_index[left["trial_id"]]["backend"], "review_version": document["version"], "left_arm": left["arm"], "right_arm": right["arm"], "outcome_for_left": rating["outcome"], "judge": judge, "review_id": packet["review_id"], "reason": rating["reason"] if not private else "Private comparison reason withheld.", "evidence": rating["evidence"] if not private else [], "privacy": "private" if private else "public"})
            if 'source_revision' in packet:
                report['pairs'][-1]['source_revision'] = packet['source_revision']
        # Evidence media comes from the already sanitized anonymous packet; its
        # source root is carried internally until export, never exposed in HTML.
        if packet.get("privacy") != "local-private":
            for entry in packet_entries.values():
                mapped = entry_map[entry["id"]]
                for turn in entry["turns"]:
                    for artifact in turn["artifacts"]:
                        report["media"].append({"trial_id": mapped["trial_id"], "case_id": mapped["case_id"], "turn": turn["turn"], "path": artifact["path"], "name": artifact.get("name", "additional-preview"), "sha256": artifact["sha256"], "size": artifact["size"], "kind": "review-evidence", "root": "packet", "review_id": packet["review_id"], "privacy": "public"})
    for (cohort_id, dimension), counts in observations.items():
        rows = [row for row in report["ratings"] if row["cohort_id"] == cohort_id and row["dimension"] == dimension]
        report["dimensions"].append({"cohort_id": cohort_id, "dimension": dimension, "score_counts": {score: counts[score] for score in ("0", "1", "2", "unverifiable")}, "observations": len(rows), "verified_observations": sum(row["score"] != "unverifiable" for row in rows), "case_count": len({row["case_id"] for row in rows}), "case_repeat_units": len({(row["case_id"], row["repeat"]) for row in rows})})
    report["cohorts"] = list(cohort_map.values())
    report["sample_sizes"] = {"independent_cases": len({row["case_id"] for row in report["trials"]}), "case_repeat_units": len({(row["case_id"], row["repeat"]) for row in report["trials"]}), "trials": len(report["trials"]), "planned_turns": sum(row["planned_turns"] for row in report["trials"]), "turn_observations": sum(row["recorded_turns"] for row in report["trials"]), "atom_observations": len(report["ratings"]), "paired_outcomes": len(report["pairs"])}
    report["coverage"] = {"ledger_closed": terminal["closed"], "planned_trials": len(schedule), "recorded_trial_results": len(result_map), "missing_trial_results": len(schedule) - len(result_map), "not_attempted_trials": sum(row["status"] == "not_attempted" for row in report["trials"]), "interrupted_without_result_trials": sum(row["status"] == "interrupted" and row["result_record"] == "missing" for row in report["trials"]), "planned_turns": report["sample_sizes"]["planned_turns"], "observed_turns": report["sample_sizes"]["turn_observations"]}
    report["coverage"]["unobserved_turns"] = max(0, report["coverage"]["planned_turns"] - report["coverage"]["observed_turns"])
    report["failures"] = dict(Counter(row["status"] for row in report["trials"]))
    for item in report["media"]:
        trial = trial_index.get(item.get("trial_id"))
        if trial:
            item["case_id"] = trial["case_id"]
        if item.get("case_id") in case_map:
            item["case_fingerprint"] = canonical_hash(case_map[item["case_id"]])
        item["experiment"] = manifest["id"]
    report["report_fingerprint"] = canonical_hash(report)
    return report


def merge_reports(reports: list[dict]) -> dict:
    """Combine compatible report schemas while retaining distinct cohort series.

    Exact duplicate report fingerprints are deduplicated. Historical raw media
    is not copied into a new bundle: the last report supplies export media, and
    every historical report retains its own hash-addressed evidence bundle.
    """
    if not reports:
        raise ValueError("At least one report is required")
    unique = []
    fingerprints = set()
    for report in reports:
        if report.get("schema_version") != 1 or report.get("kind") != "skill-benchmark-report":
            raise ValueError("Incompatible historical report schema")
        fingerprint = report.get("report_fingerprint", canonical_hash(report))
        if fingerprint not in fingerprints:
            unique.append(report)
            fingerprints.add(fingerprint)
    merged = json.loads(json.dumps(unique[-1]))
    merged.update(experiment="history", current_experiment=unique[-1].get("current_experiment", unique[-1]["experiment"]), experiments=[], case_contexts=[], trials=[], ratings=[], pairs=[], dimensions=[], cohorts=[], history=[])
    contexts = {}
    cohorts = {}
    cases = set()
    case_repeats = set()
    dimension_counts = defaultdict(Counter)
    for report in unique:
        experiment = report["experiment"]
        merged["experiments"].extend(report.get("experiments", [{"id": experiment, "commit_provenance": {}}]))
        for context in report.get("case_contexts", []):
            key = context["case_fingerprint"]
            if key in contexts and contexts[key] != context:
                raise ValueError("Conflicting frozen case context fingerprint")
            contexts[key] = context
        cohort_map = {cohort["id"]: cohort for cohort in report["cohorts"]}
        execution_conditions = {key: canonical_hash({field: value for field, value in cohort.items() if field not in {"id", "judge"}}) for key, cohort in cohort_map.items()}
        for key, value in cohort_map.items():
            if key in cohorts and cohorts[key] != value:
                raise ValueError("Cohort fingerprint collision in history")
            cohorts[key] = value
        for row in report["trials"]:
            item = {**row, "id": experiment + "/" + row["id"], "experiment": experiment}
            merged["trials"].append(item)
            cohort = cohort_map[row["cohort_id"]]
            case_key = (cohort["suite_fingerprint"], cohort["case_fingerprint"])
            cases.add(case_key)
            case_repeats.add((case_key, experiment, row["repeat"]))
        for row in report["ratings"]:
            merged["ratings"].append({**row, "trial_id": experiment + "/" + row["trial_id"], "experiment": experiment})
            dimension_counts[(row["cohort_id"], row["dimension"])][str(row["score"])] += 1
        for row in report["pairs"]:
            item = {**row, "experiment": experiment}
            for key in ("left_trial_id", "right_trial_id"):
                if key in item:
                    item[key] = experiment + "/" + item[key]
            merged["pairs"].append(item)
        for cohort_id in cohort_map:
            ratings = [row for row in report["ratings"] if row["cohort_id"] == cohort_id]
            linked_trial_ids = {row["trial_id"] for row in ratings}
            trials = [row for row in report["trials"] if execution_conditions.get(row["cohort_id"]) == execution_conditions[cohort_id] or row["id"] in linked_trial_ids]
            if not trials and not ratings:
                continue
            counts = Counter(str(row["score"]) for row in ratings)
            planned = [row.get("planned_turns") for row in trials]
            merged["history"].append({"experiment": experiment, "report_fingerprint": report.get("report_fingerprint", "unknown"), "cohort_id": cohort_id, "independent_cases": 1, "trials": len(trials), "trial_status_counts": dict(Counter(row["status"] for row in trials)), "case_repeat_units": len({row["repeat"] for row in trials + ratings}), "planned_turns": sum(planned) if all(type(value) is int and value >= 0 for value in planned) else None, "turn_observations": sum(row.get("recorded_turns", sum(turn.get("evidence_status") != "missing-result" for turn in row["turns"])) for row in trials), "atom_observations": len(ratings), "score_counts": {score: counts[score] for score in ("0", "1", "2", "unverifiable")}, "seconds": sum(row["seconds"] for row in trials) if trials and all(row["seconds"] is not None for row in trials) else None})
    for (cohort_id, dimension), counts in dimension_counts.items():
        rows = [row for row in merged["ratings"] if row["cohort_id"] == cohort_id and row["dimension"] == dimension]
        merged["dimensions"].append({"cohort_id": cohort_id, "dimension": dimension, "score_counts": {score: counts[score] for score in ("0", "1", "2", "unverifiable")}, "observations": len(rows), "verified_observations": sum(row["score"] != "unverifiable" for row in rows), "case_count": 1, "case_repeat_units": len({(row["experiment"], row["repeat"]) for row in rows})})
    merged["cohorts"] = list(cohorts.values())
    merged["case_contexts"] = list(contexts.values())
    latest = unique[-1]["experiment"]
    for item in merged["media"]:
        item["experiment"] = latest
        if "trial_id" in item:
            if item.get("root") == "trial":
                item["_source_trial_id"] = item["trial_id"]
            item["trial_id"] = latest + "/" + item["trial_id"]
    planned = [row.get("planned_turns") for row in merged["trials"]]
    planned_total = sum(planned) if all(type(value) is int and value >= 0 for value in planned) else None
    observed_total = sum(row.get("recorded_turns", sum(turn.get("evidence_status") != "missing-result" for turn in row["turns"])) for row in merged["trials"])
    merged["sample_sizes"] = {"independent_cases": len(cases), "case_repeat_units": len(case_repeats), "trials": len(merged["trials"]), "planned_turns": planned_total, "turn_observations": observed_total, "atom_observations": len(merged["ratings"]), "paired_outcomes": len(merged["pairs"])}
    known_records = all(row.get("result_record") in {"present", "missing"} for row in merged["trials"])
    merged["coverage"] = {"planned_trials": len(merged["trials"]), "recorded_trial_results": sum(row.get("result_record") == "present" for row in merged["trials"]) if known_records else None, "missing_trial_results": sum(row.get("result_record") == "missing" for row in merged["trials"]) if known_records else None, "planned_turns": planned_total, "observed_turns": observed_total, "unobserved_turns": max(0, planned_total - observed_total) if planned_total is not None else None}
    merged["historical_media_omitted"] = sum(len(report["media"]) for report in unique[:-1])
    merged["limitations"].append("Historical media remains in its original report bundle; only current-run media is included here.")
    merged["failures"] = dict(Counter(row["status"] for row in merged["trials"]))
    merged["fingerprint"] = canonical_hash(sorted(fingerprints))
    merged["report_fingerprint"] = canonical_hash({key: value for key, value in merged.items() if key != "report_fingerprint"})
    return merged


from .report_view import STYLE as _STYLE, SCRIPT as _SCRIPT, render_document


def render_html(report: dict) -> str:
    """Use the trusted offline renderer; style/script remain version-bound."""
    return render_document(report, style=_STYLE, script=_SCRIPT)


def _assert_public(value: dict) -> None:
    patterns = (r"(?i)(?:api[_ -]?key|access[_ -]?token|authorization|bearer)[\"'\s]*[=:]", r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", r"(?:/home/|/root/|\.codex/|\.agents/skills/)")
    forbidden_keys = {"thread_id", "session_id", "raw_logs", "events", "credentials", "auth", "api_key", "access_token", "private_key", "blind_key"}
    def visit(item):
        if isinstance(item, dict):
            if forbidden_keys.intersection(item):
                raise ValueError("Public report contains a private field")
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str) and any(re.search(pattern, item) for pattern in patterns):
            raise ValueError("Public report contains a private identifier or credential-like value")
    visit(value)


def export_report(report: dict, destination: str | Path, *, media_root: str | Path | None = None, packet_roots: dict[str, str | Path] | None = None, public_roots: dict[str, str | Path] | None = None, max_file_bytes: int = 8 * 1024 * 1024, max_total_bytes: int = 64 * 1024 * 1024) -> dict:
    """Write a new sanitized HTML/JSON bundle and allowlisted raster media only."""
    if report.get("kind") == "skill-benchmark-local-report" or report.get("visibility") == "local-private":
        raise ValueError("Local-private reports cannot use the public export command")
    dest = Path(destination)
    if dest.exists() or dest.is_symlink():
        raise ValueError("Report destination must be new")
    # Clone only JSON-compatible report data; drop source locations before the
    # public leak check and replace them with content-addressed output names.
    public = json.loads(json.dumps(report))
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".report-export-", dir=dest.parent))
    total = 0
    try:
        retained_media = []
        for item in public.get("media", []):
            if item.get("privacy") != "public":
                raise ValueError("Private media cannot be exported to a public report")
            if media_root is None and item.get("root") != "public":
                raise ValueError("Report media requires its declared checked root")
            root = Path(media_root) if media_root is not None else None
            relative = item["path"]
            if item.get("root") == "public":
                identity = item.pop("_public_bundle", None)
                if not public_roots or identity not in public_roots:
                    raise ValueError("Historical public image bundle root is missing")
                root = Path(public_roots[identity])
            elif item.get("root") == "trial":
                # trial identifiers are lexical single components, not paths.
                trial_id = item.pop("_source_trial_id", item["trial_id"])
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", trial_id) or trial_id in {".", ".."}:
                    raise ValueError("Invalid trial identifier")
                relative = "trials/" + trial_id + "/" + relative
            elif item.get("root") == "packet":
                if not packet_roots or item["review_id"] not in packet_roots:
                    raise ValueError("Review evidence packet root is missing")
                root = Path(packet_roots[item["review_id"]])
            _, data = checked_file(root, relative, expected_hash=item["sha256"], expected_size=item.get("size"), max_bytes=max_file_bytes)
            validation = preview_validation(item["path"], data)
            if not validation["allowed"]:
                if item.get("kind") not in {"preview", "review-evidence"}:
                    raise ValueError("Reference or source proof image failed its content check")
                withheld = {key: item[key] for key in ("name", "case_id", "trial_id", "turn", "sha256", "size", "review_id") if key in item}
                withheld["withheld_reason"] = validation["withheld_reason"]
                public.setdefault("withheld_previews", []).append(withheld)
                continue
            suffix = validation["suffix"]
            if suffix == '.png':
                from .public_media import strip_png_metadata, TRANSFORMATION
                clean, removed = strip_png_metadata(data)
                if removed:
                    item.update(source_sha256=item['sha256'], source_size=len(data),
                                transformation={'id': TRANSFORMATION, 'removed_chunks': removed},
                                sha256=hashlib.sha256(clean).hexdigest())
                    data = clean
            target = "media/" + item["sha256"] + suffix
            output = staging / target
            if not output.exists():
                total += len(data)
                if total > max_total_bytes:
                    raise ValueError("Report media exceeds the aggregate byte limit")
                output.parent.mkdir(exist_ok=True)
                output.write_bytes(data)
            item["export_path"] = target
            item["size"] = len(data)
            item["container_check"] = validation["container_check"]
            item.pop("path", None)
            item.pop("root", None)
            retained_media.append(item)
        public["media"] = retained_media
        derivatives = {item['source_sha256']: item for item in retained_media if item.get('transformation', {}).get('id') == 'png-metadata-removal-v1'}
        for row in public.get('ratings', []) + public.get('pairs', []):
            for evidence in row.get('evidence', []):
                derivative = derivatives.get(evidence.get('sha256'))
                if derivative:
                    evidence.update(public_path=derivative['export_path'], public_sha256=derivative['sha256'])
        public.setdefault("coverage", {})["withheld_preview_count"] = len(public.get("withheld_previews", []))
        _assert_public(public)
        from .changes import validate_report_changes
        validate_report_changes(public)
        public["sanitized"] = True
        public["report_fingerprint"] = canonical_hash({key: value for key, value in public.items() if key != "report_fingerprint"})
        (staging / "report.json").write_text(json.dumps(public, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (staging / "index.html").write_text(render_html(public), encoding="utf-8")
        staging.rename(dest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"schema_version": 1, "sanitized": True, "report_fingerprint": public["report_fingerprint"], "files": ["report.json", "index.html"] + sorted({item["export_path"] for item in public.get("media", [])}), "media_bytes": total, "withheld_previews": len(public.get("withheld_previews", []))}


def validate_public_bundle(root: str | Path, *, max_file_bytes: int = 8 * 1024 * 1024, max_total_bytes: int = 64 * 1024 * 1024) -> dict:
    """Check a downloaded sanitized artifact without running its HTML or sources."""
    base = Path(root)
    _, data = checked_file(base, "report.json", max_bytes=max_file_bytes)
    public = json.loads(data)
    if public.get("schema_version") != 1 or public.get("kind") != "skill-benchmark-report" or public.get("sanitized") is not True or public.get("visibility") == "local-private" or public.get("privacy") == "local-private":
        raise ValueError("Downloaded artifact is not a sanitized benchmark report")
    _assert_public(public)
    from .changes import validate_report_changes
    validate_report_changes(public)
    expected = {"index.html", "report.json"}
    total = len(data)
    media_hashes = {}
    for item in public.get("media", []):
        from .public_media import validate_derivation
        validate_derivation(item)
        name = item["export_path"]
        if not re.fullmatch(r"media/[0-9a-f]{64}\.(?:png|jpg|webp|gif)", name) or item["sha256"] not in name:
            raise ValueError("Public media is not content addressed")
        if name in media_hashes and media_hashes[name] != item["sha256"]:
            raise ValueError("Conflicting public media hashes")
        if name not in media_hashes:
            _, image = checked_file(base, name, expected_hash=item["sha256"], expected_size=item["size"], max_bytes=max_file_bytes)
            if not preview_validation(name, image)["allowed"]:
                raise ValueError("Downloaded public image failed its content check")
            if name.endswith('.png'):
                from .public_media import strip_png_metadata
                if strip_png_metadata(image)[1]:
                    raise ValueError('Public PNG metadata must be removed before publication')
            total += len(image)
        media_hashes[name] = item["sha256"]
        expected.add(name)
    _, html_data = checked_file(base, "index.html", max_bytes=max_file_bytes)
    total += len(html_data)
    if total > max_total_bytes:
        raise ValueError("Downloaded public artifact exceeds aggregate byte limit")
    if html_data.decode("utf-8") != render_html(public):
        raise ValueError("Downloaded HTML differs from the trusted escaped renderer")
    actual = set()
    for path in base.rglob("*"):
        if path.is_symlink():
            raise ValueError("Downloaded artifact contains a symbolic link")
        if path.is_file():
            actual.add(path.relative_to(base).as_posix())
        elif not path.is_dir():
            raise ValueError("Downloaded artifact contains a special file")
    if actual != expected:
        raise ValueError("Downloaded artifact contains files outside its public allowlist")
    fingerprint = canonical_hash({key: value for key, value in public.items() if key != "report_fingerprint"})
    if public.get("report_fingerprint") != fingerprint:
        raise ValueError("Downloaded report fingerprint is inconsistent")
    return {"valid": True, "files": len(actual), "bytes": total, "report_fingerprint": fingerprint}
