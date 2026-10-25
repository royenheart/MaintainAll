"""Explicit local-private report export; never accepted by public publication."""
from __future__ import annotations

import json
import html
from pathlib import Path
import re
import shutil
import stat

from . import report
from .review import canonical_hash, checked_file, MEDIA_SUFFIXES, preview_validation, validate_declared_note, MAX_NOTE_BYTES, MAX_NOTE_TOTAL_BYTES
from .store import private_directory

LOCAL_KIND = "skill-benchmark-local-report"
LOCAL_VISIBILITY = "local-private"
MAX_LOCAL_BYTES = 256 * 1024 * 1024


def _task_text(value):
    """Redact local identifiers in declared task text, never copy session traces."""
    if isinstance(value, dict):
        return {key: _task_text(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_task_text(child) for child in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r"(?im)^.*(?:api[_ -]?key|access[_ -]?token|authorization|bearer)[\"'\s]*[=:].*$", "[credential-bearing text withheld]", value)
    value = re.sub(r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b", "[private identifier]", value)
    return re.sub(r"(?:/home/|/root/|\.codex/|\.agents/skills/)[^\s\"'<>]*", "[private path]", value)


def build_local_report(manifest: dict, results: list[dict], reviews: list[dict] | None = None, *, execution_events=None, skill_root=None, evidence_scope='legacy') -> dict:
    """Extend the public allowlist with authorized private raster evidence.

    Original task and cohort fingerprints stay intact. Review mappings are used
    to restore original judgments but never enter the report. Source programs,
    arbitrary solver notes, raw events and session identifiers are not copied.
    """
    local = report.build_report(manifest, results, reviews, execution_events=execution_events, skill_root=skill_root)
    if evidence_scope not in {'legacy', 'failed-turn-v1'}:
        raise ValueError('Unsupported local failed-turn evidence scope')
    failure_packets = [bundle for bundle in reviews or [] if bundle['packet'].get('evidence_scope') == 'failed-turn-v1']
    if failure_packets:
        evidence_scope = 'failed-turn-v1'
    local.update(kind=LOCAL_KIND, visibility=LOCAL_VISIBILITY, privacy=LOCAL_VISIBILITY)
    local['text_deliverables'] = []
    cases = {case["id"]: case for case in manifest["cases"]}
    local["case_contexts"] = []
    for case in cases.values():
        allowed = _task_text({key: value for key, value in case.items() if key not in {"visibility", "assets", "attachments"}})
        context = report._case_context(allowed)
        context.update(case_fingerprint=canonical_hash(case), visibility=LOCAL_VISIBILITY)
        local["case_contexts"].append(context)
    scheduled = {row["trial_id"]: row for row in manifest["schedule"]}
    original_private = {trial["id"] for trial in local["trials"] if trial["privacy"] == "private"}
    for trial in local["trials"]:
        trial["privacy"] = LOCAL_VISIBILITY
    for result in results:
        trial_id = result["trial_id"]
        if trial_id not in original_private:
            continue
        row, case = scheduled[trial_id], cases[scheduled[trial_id]["case_id"]]
        for turn in result.get("turns", []):
            number = turn["turn"]
            declared = {item["path"] for item in case.get("turns", [])[number - 1].get("artifacts", [])} if 1 <= number <= len(case.get("turns", [])) else set()
            for artifact in turn.get("artifacts", []):
                if Path(artifact.get("path", "")).suffix.lower() in MEDIA_SUFFIXES:
                    local["media"].append({"trial_id": trial_id, "case_id": case["id"], "turn": number, "name": artifact["path"] if artifact["path"] in declared else "additional-preview", "path": artifact["snapshot"], "sha256": artifact["sha256"], "size": artifact["size"], "kind": "preview", "root": "trial"})
            for proof in turn.get("source_verification", []):
                native = proof.get("format") in {"html", "blend"}
                source_name = next((item['path'] for item in turn.get('artifacts', []) if item.get('sha256') == proof.get('source_sha256')), 'source')
                for label, image in proof.get("rendered", {}).items():
                    if label not in {"source", "edited"} and not (native and re.fullmatch(r"[a-zA-Z0-9_.-]{1,96}", label)):
                        raise ValueError("Unsupported local source proof render type")
                    capture_label = image.get('label', label)
                    item = {"trial_id": trial_id, "case_id": case["id"], "turn": number, "name": "Independent capture / " + capture_label if native else source_name + ' / ' + capture_label, "path": image["path"], "sha256": image["sha256"], "size": image["size"], "kind": "verifier-edit" if native and label in {"edited", "edited-front"} else "independent-capture" if native else "source-rebuild" if label == "source" else "one-fill-edit", "root": "run"}
                    item.update({key: image[key] for key in ('profile', 'time_ms', 'requested_time_ms', 'viewport', 'label') if key in image})
                    local["media"].append(item)
    for case in cases.values():
        if not any(row["case_id"] == case["id"] and row["trial_id"] in original_private for row in scheduled.values()):
            continue
        for asset in case.get("assets", case.get("attachments", [])):
            if Path(asset.get("snapshot", asset.get("path", ""))).suffix.lower() in MEDIA_SUFFIXES:
                local["media"].append({"case_id": case["id"], "name": asset["id"], "path": asset.get("snapshot", asset["path"]), "sha256": asset["sha256"], "size": asset.get("size"), "root": "run", "kind": "reference", "license": _task_text(asset.get("license", "unspecified"))})
    for bundle in reviews or []:
        packet, document, mapping = bundle["packet"], bundle["document"], bundle["arm_map"]
        entry_map = mapping["entries"]
        if packet.get('view') in {'notes-process', 'notes-process-v2'}:
            for entry in packet['entries']:
                mapped = entry_map[entry['id']]
                case = cases[mapped['case_id']]
                result = next((value for value in results if value['trial_id'] == mapped['trial_id']), None)
                for turn in entry['turns']:
                    declarations = {value['path']: value for value in case['turns'][turn['turn'] - 1]['artifacts']}
                    frozen_turn = next((value for value in (result or {}).get('turns', []) if value['turn'] == turn['turn']), {})
                    inventory = {value['path']: value for value in frozen_turn.get('artifacts', [])}
                    for note in turn.get('notes', []):
                        data = validate_declared_note(note, require_path=packet['view'] == 'notes-process-v2')
                        declaration, artifact = declarations.get(note['name'], {}), inventory.get(note['name'], {})
                        if declaration.get('kind') != 'notes' or declaration.get('format') != note['format'] or artifact.get('sha256') != note.get('source_sha256', note['sha256']) or artifact.get('review_safe') is False:
                            raise ValueError('Review text is not the declared sealed note for this trial and turn')
                        item = {key: note[key] for key in ('name', 'kind', 'format', 'sha256', 'text', 'source')}
                        item.update({key: note[key] for key in ('source_sha256', 'source_size', 'transformation') if key in note})
                        item.update(trial_id=mapped['trial_id'], case_id=mapped['case_id'], case_fingerprint=canonical_hash(case), turn=turn['turn'], size=len(data), review_id=packet['review_id'], review_version=document['version'], review_view=packet['view'], privacy=LOCAL_VISIBILITY)
                        if 'path' in note:
                            item['packet_path'] = note['path']
                        local['text_deliverables'].append(item)
        for rating in document["ratings"]:
            trial_id = entry_map[rating["entry"]]["trial_id"]
            row = next(item for item in local["ratings"] if item["trial_id"] == trial_id and item["turn"] == rating["turn"] and item["atom"] == rating["atom"] and item["review_id"] == packet["review_id"] and item["review_version"] == document["version"])
            row.update(reason=rating["reason"], evidence=rating["evidence"], privacy=LOCAL_VISIBILITY)
        for rating in document["pairs"]:
            pair = next(item for item in packet["pairs"] if item["id"] == rating["pair"])
            left, right = entry_map[pair["left"]], entry_map[pair["right"]]
            row = next(item for item in local["pairs"] if item["left_trial_id"] == left["trial_id"] and item["right_trial_id"] == right["trial_id"] and item["review_id"] == packet["review_id"] and item["review_version"] == document["version"])
            row.update(reason=rating["reason"], evidence=rating["evidence"], privacy=LOCAL_VISIBILITY)
        if packet.get("privacy") == LOCAL_VISIBILITY:
            for entry in packet["entries"]:
                mapped = entry_map[entry["id"]]
                for turn in entry["turns"]:
                    for artifact in turn["artifacts"]:
                        local["media"].append({"trial_id": mapped["trial_id"], "case_id": mapped["case_id"], "turn": turn["turn"], "path": artifact["path"], "name": artifact.get("name", "additional-preview"), "sha256": artifact["sha256"], "size": artifact["size"], "kind": "independent-capture" if artifact.get('kind') == 'independent-source-capture' else "review-evidence", "root": "packet", "review_id": packet["review_id"]})
    for item in local["media"]:
        item.update(privacy=LOCAL_VISIBILITY, experiment=manifest["id"], case_fingerprint=canonical_hash(cases[item["case_id"]]))
    if evidence_scope != 'legacy':
        _apply_failure_scope(local, results, failure_packets, skill_root)
    local["limitations"].append("Local-private evidence is authorized for local inspection only and cannot enter public report publication.")
    local["report_fingerprint"] = canonical_hash({key: value for key, value in local.items() if key != "report_fingerprint"})
    return local


def _apply_failure_scope(local, results, bundles, run_root):
    from .failure_evidence import inspect_turn_evidence, persisted_inventory, turn_evidence_scope
    local['evidence_scope'] = 'failed-turn-v1'
    bound = {}
    for bundle in bundles:
        mapping = bundle['arm_map']['entries']
        for entry in bundle['packet']['entries']:
            for turn in entry['turns']:
                bound[(mapping[entry['id']]['trial_id'], turn['turn'])] = turn
    unavailable = set()
    index = {trial['id']: trial for trial in local['trials']}
    for result in results:
        for source in result.get('turns', []):
            status = source.get('status', result['status'])
            if status not in {'failed', 'interrupted'}:
                continue
            key = (result['trial_id'], source['turn'])
            frozen = bound.get(key)
            checked = {**source, 'status': status}
            if frozen and 'cli_event_evidence' in frozen:
                checked['cli_event_evidence'] = frozen['cli_event_evidence']
            if run_root is not None:
                scope = inspect_turn_evidence(run_root, result['trial_id'], checked, backend_id=result.get('backend', {}).get('id'))
                if frozen and scope['evidence_status'] != frozen['evidence_status']:
                    raise ValueError('Failed-turn stream differs from the frozen review condition')
            elif frozen:
                scope = turn_evidence_scope(status, frozen.get('cli_event_evidence', {}))
            else:
                raise ValueError('Local failed-turn inspection requires its run root or a frozen scoped packet')
            record = next(turn for turn in index[result['trial_id']]['turns'] if turn['turn'] == source['turn'])
            record.update(evidence_status=scope['evidence_status'], cli_event_evidence=scope['cli_event_evidence'])
            if scope['withhold_turn_artifacts']:
                unavailable.add(key)
                record['persisted_artifact_inventory'] = persisted_inventory(source.get('artifacts', []), kind='persisted-artifact-withheld')
                record['persisted_source_proof_inventory'] = persisted_inventory([image for proof in source.get('source_verification', []) for image in proof.get('rendered', {}).values()], kind='persisted-reopen-withheld')
                record.update(persisted_delivery_pass=record.get('delivery_pass'), delivery_pass=None, source_editability_verified=None, source_proofs=[])
    local['media'] = [item for item in local['media'] if (item.get('trial_id'), item.get('turn')) not in unavailable]
    local['text_deliverables'] = [item for item in local['text_deliverables'] if (item['trial_id'], item['turn']) not in unavailable]
    if any((row['trial_id'], row['turn']) in unavailable and row['score'] != 'unverifiable' for row in local['ratings']):
        raise ValueError('Persisted failed-turn files cannot support frozen ordinal ratings; use a new scoped review')


def _local_identity(value):
    if value.get("schema_version") != 1 or value.get("kind") != LOCAL_KIND or value.get("visibility") != LOCAL_VISIBILITY or value.get("privacy") != LOCAL_VISIBILITY:
        raise ValueError("An explicitly local-private report is required")
    if any(item.get("privacy") != LOCAL_VISIBILITY for field in ("trials", "ratings", "pairs", "media", "text_deliverables") for item in value.get(field, [])):
        raise ValueError("Local report records must retain their local-private marker")


def _validate_text_deliverables(value):
    total = 0
    trials = {item['id'] for item in value.get('trials', [])}
    for item in value.get('text_deliverables', []):
        data = validate_declared_note(item)
        if item.get('trial_id') not in trials or item.get('review_view') not in {'notes-process', 'notes-process-v2'} or type(item.get('turn')) is not int or item['turn'] < 1 or type(item.get('size')) is not int or item['size'] != len(data):
            raise ValueError('Local text must retain its validated notes-process condition and trial')
        total += len(data)
    if total > MAX_NOTE_TOTAL_BYTES:
        raise ValueError('Local declared text exceeds its aggregate byte limit')


_TEXT_SCRIPT = r"""
function renderLocalTextDeliverables(body,slots,turn){
  const selected=slots.map(slot=>({slot,notes:(data.text_deliverables||[]).filter(note=>slot.trial&&note.trial_id===slot.trial.id&&note.turn===turn&&(!state.review_view||note.review_view===state.review_view))}));
  if(!selected.some(group=>group.notes.length))return;
  const box=details('Declared text deliverables');box.append(node('p','These are reviewed task outputs from the selected notes-process condition. Self-evaluation and explanatory captions remain solver claims.','caption'));
  const grid=node('div',undefined,'evidence-columns');
  for(const {slot,notes} of selected){const column=node('div',undefined,'evidence-column');column.append(node('h4',slot.trial?armLabel(slot.arm,view.experimentOf(slot.trial)):'No baseline'));
    for(const note of notes){const document=details(note.name),identity=node('p',note.sha256,'caption');document.append(identity);if(note.transformation)document.append(node('p',note.transformation.id+' · '+(note.transformation.changed?'Local paths redacted':'Text unchanged')+' · raw source SHA-256 '+note.source_sha256,'caption'));document.append(node('pre',note.text,'task-text'));if(/^text\/[0-9a-f]{64}\.txt$/.test(note.export_path||'')){const link=node('a','Open reviewed text');link.href=note.export_path;link.target='_blank';link.rel='noopener';document.append(link);}column.append(document);}
    if(!notes.length)column.append(node('p','No reviewed text is available under this condition.','muted'));grid.append(column);
  }box.append(grid);body.append(box);
}
"""


def _text_script(script):
    original = 'renderAlignedEvidence(body,slots,chosen.turn,context);'
    if script.count(original) != 1:
        raise ValueError('Trusted report evidence layout changed; local text adapter needs review')
    return _TEXT_SCRIPT + '\n' + script.replace(original, original + 'renderLocalTextDeliverables(body,slots,chosen.turn);', 1)


def _local_script(script: str) -> str:
    """Adapt one visibility guard without changing public renderer bytes."""
    original = "if(!context||context.visibility!=='public')return [];"
    local = "if(!context||(context.visibility!=='public'&&!(context.visibility==='local-private'&&source.kind==='skill-benchmark-local-report'&&source.visibility==='local-private')))return [];"
    if script.count(original) != 1:
        raise ValueError("Trusted report reference guard changed; local renderer needs review")
    script = script.replace(original, local, 1)
    guard = "context?.visibility==='public'?"
    if script.count(guard) != 2:
        raise ValueError('Trusted atom/output visibility guards changed; local renderer needs review')
    return script.replace(guard, "(context?.visibility==='public'||(context?.visibility==='local-private'&&source.kind==='skill-benchmark-local-report'&&source.visibility==='local-private'))?")


_FAILURE_SCRIPT = r"""
function renderLocalFailureScope(body,slots,turn){
  const labels={'failed-no-model-output':'No model-output event was observed in the verified CLI stream. Persisted files and reopened images are withheld for this turn; applicable requirements remain unverifiable.','partial-model-output':'Partial model output was observed before this failed turn stopped. These files are a partial snapshot and may include earlier files; model activity does not prove that every file changed.','unknown-failed-output':'Model-output scope could not be verified for this failed turn. Available files are retained without claiming a new final output.'};
  for(const slot of slots){const record=slot.trial?.turns.find(value=>value.turn===turn),message=labels[record?.evidence_status];if(!message)continue;const box=node('div',undefined,'coverage-note tone-unknown');box.append(node('strong',roleLabel(slot.arm)+' · '+statusLabel(record.status)),node('p',message));const inventory=details('Failed-turn evidence scope',node('pre',JSON.stringify({evidence_status:record.evidence_status,cli_event_evidence:record.cli_event_evidence,persisted_artifact_inventory:record.persisted_artifact_inventory||[],persisted_source_proof_inventory:record.persisted_source_proof_inventory||[]},null,2)));box.append(inventory);body.insertBefore(box,body.querySelector('.evidence-headers'));}
}
"""


def _failure_script(script):
    original = 'renderAlignedEvidence(body,slots,chosen.turn,context);'
    if script.count(original) != 1:
        raise ValueError('Trusted failed-turn layout adapter needs review')
    return _FAILURE_SCRIPT + '\n' + script.replace(original, original + 'renderLocalFailureScope(body,slots,chosen.turn);', 1)


def _one_version_screen(value):
    by_experiment = {}
    for trial in value.get('trials', []):
        by_experiment.setdefault(trial.get('experiment', value['experiment']), set()).add(trial['arm'])
    return bool(by_experiment) and all(len(arms) == 1 for arms in by_experiment.values())


_TESTED_VERSION_DEFINITION = 'The exact frozen skill commit or snapshot used for these runs.'
_ONE_VERSION_SCRIPT = r"""
function localSingleVersionView(view){
  const rows=view.experiments.flatMap(experiment=>{const arms=[...new Set((view.source.trials||[]).filter(t=>view.experimentOf(t)===experiment).map(t=>t.arm))];if(arms.length!==1)return [];const version=view.versionInfo(experiment,arms[0]);return version?[{experiment,version}]:[];});
  view.versionOptions=state=>{
    const current=rows.find(row=>row.experiment===state.experiment)?.version||null;
    return {candidate:current,baseline:null,candidates:[...new Map(rows.map(row=>[row.version.id,row.version])).values()],baselines:[],runs:rows.filter(row=>row.version.id===current?.id).map(row=>row.experiment)};
  };
  view.chooseVersions=(state,versionId,baselineId,runId)=>{
    if(baselineId)return null;
    const matches=rows.filter(row=>row.version.id===versionId);
    const chosen=(runId?matches.find(row=>row.experiment===runId):null)||matches.find(row=>row.experiment===state.experiment)||matches.at(-1);
    if(!chosen||runId&&chosen.experiment!==runId)return null;
    const review_view=(view.source.ratings||[]).some(row=>view.experimentOf(row)===chosen.experiment&&view.value(row,'review_view')==='artifact-only')?'artifact-only':'';
    return {...view.defaults(),experiment:chosen.experiment,baseline:'',review_view};
  };
  return view;
}
function localVersionSlots(unit,skill){return unit.filter(trial=>!skill||trial.arm===skill).map(trial=>({arm:trial.arm,trial}));}
function applySingleVersionLayout(){
  const overview=document.getElementById('overview-charts');
  for(const panel of overview.querySelectorAll('.chart-panel')){const heading=panel.querySelector('h3'),label=(heading?.dataset.headingText||heading?.textContent||'').replace(/^\d+(?:\.\d+)*\.\s*/, '');if(label==='Comparison by case')panel.remove();}
  helpDefinitions.set('tested version',{label:'Tested version',definition:'The exact frozen skill commit or snapshot used for these runs.'});
  helpDefinitions.set('versions and filters',{label:'Versions and filters',definition:'Choose the exact tested skill, evaluation and task whose recorded results are displayed.'});
}
"""


def _one_version_script(script):
    replacements = {
        'createReportView(data)': 'localSingleVersionView(createReportView(data))',
        "const roleLabel=arm=>arm==='candidate'?'Candidate':arm==='none'?'No skill':'Baseline';": "const roleLabel=arm=>'Tested version';",
        "pair.append(versionCard(baseline,experiment),versionCard('candidate',experiment));": "for(const arm of [...new Set((data.trials||[]).filter(t=>view.experimentOf(t)===experiment).map(t=>t.arm))])pair.append(versionCard(arm,experiment));",
        "const slots=state.skill?unit.filter(t=>t.arm===state.skill).map(trial=>({arm:trial.arm,trial})):[{arm:state.baseline,trial:baseline},{arm:'candidate',trial:candidate}];": "const slots=localVersionSlots(unit,state.skill);",
        'summary.append(outcomes);return summary;': 'return summary;',
        'renderSkillDiff();numberReportHeadings();}': 'renderSkillDiff();applySingleVersionLayout();numberReportHeadings();}',
        "Array.from(section.querySelectorAll('h3,[role=\"heading\"][aria-level=\"3\"]')).entries()": "Array.from(section.querySelectorAll('h3,[role=\"heading\"][aria-level=\"3\"]')).filter(heading=>!heading.closest('[hidden]')).entries()",
        'References, outputs and frozen judgments for this task. Select the same repeat and turn to compare tested versions.': 'References, outputs and frozen judgments for this task. Select its repeat and turn to inspect the tested version.',
    }
    for original, replacement in replacements.items():
        if script.count(original) != 1:
            raise ValueError('Trusted one-version report layout changed; local adapter needs review')
        script = script.replace(original, replacement, 1)
    return _ONE_VERSION_SCRIPT + '\n' + script


def _one_version_html(rendered):
    rendered = rendered.replace('<section id="version-comparison">', '<section id="version-comparison" hidden>', 1)
    rendered = rendered.replace('<li><a href="#version-comparison">', '<li hidden><a href="#version-comparison">', 1)
    rendered = rendered.replace('<label>Candidate commit<select', '<label>Tested version<select', 1)
    rendered = rendered.replace('id="candidate-commit-select" aria-label="Candidate commit"', 'id="candidate-commit-select" aria-label="Tested version"', 1)
    rendered = rendered.replace('<label>Baseline commit<select', '<label hidden>Baseline commit<select', 1)
    rendered = rendered.replace('<h3>Skill changes</h3><details id="skill-diff">', '<h3 hidden>Skill changes</h3><details id="skill-diff" hidden>', 1)
    for number, identifier, label in ((3, 'case-evidence', 'Inspect the case evidence'), (4, 'commit-history', 'Evaluation history')):
        rendered = rendered.replace('<h2>' + str(number + 1) + '. ' + label + '</h2>', '<h2>' + str(number) + '. ' + label + '</h2>', 1)
        rendered = rendered.replace('href="#' + identifier + '">' + str(number + 1) + '. ' + label, 'href="#' + identifier + '">' + str(number) + '. ' + label, 1)
    for term in ('Candidate', 'Baseline', 'Candidate versus baseline', 'Version comparison', 'Paired judgments', 'Comparison by case', 'Skill changes'):
        rendered = re.sub(r'<tr><th scope="row">' + re.escape(html.escape(term)) + r'</th><td>.*?</td></tr>', '', rendered, count=1, flags=re.S)
    rendered = re.sub(r'(<tr><th scope="row">Versions and filters</th><td>).*?(</td></tr>)', r'\1Choose the exact tested skill, evaluation and task whose recorded results are displayed.\2', rendered, count=1, flags=re.S)
    row = '<tr><th scope="row">Tested version</th><td>' + html.escape(_TESTED_VERSION_DEFINITION) + '</td></tr>'
    return rendered.replace('<tbody>', '<tbody>' + row, 1)


_CAPTION_SCRIPT = r"""
function localImageCaption(item){const parts=[item.name||'Image'];if(item.profile)parts.push(item.profile);if(Number.isFinite(item.time_ms))parts.push('actual '+item.time_ms+' ms');if(Number.isFinite(item.requested_time_ms))parts.push('requested '+item.requested_time_ms+' ms');return parts.join(' · ');}
"""


def _caption_script(script):
    original = "f.append(img,node('figcaption',item.name||'Image'));"
    if script.count(original) != 1:
        raise ValueError('Trusted image caption changed; local adapter needs review')
    return _CAPTION_SCRIPT + '\n' + script.replace(original, "f.append(img,node('figcaption',localImageCaption(item)));", 1)


def render_local_html(value: dict) -> str:
    """Use the compact public layout with a bounded local visibility adapter."""
    _local_identity(value)
    _validate_text_deliverables(value)
    script = _local_script(report._SCRIPT)
    script = _caption_script(script)
    if value.get('text_deliverables'):
        script = _text_script(script)
    if value.get('evidence_scope') == 'failed-turn-v1':
        script = _failure_script(script)
    one_version = _one_version_screen(value)
    style = report._STYLE
    if one_version:
        script = _one_version_script(script)
        style += '\n#overview-charts{grid-template-columns:1fr}.evidence-columns{grid-template-columns:1fr}\n'
    rendered = report.render_document(value, style=style, script=script)
    if one_version:
        rendered = _one_version_html(rendered)
    return rendered.replace("<main>", '<main><p class="coverage-note tone-stopped">Local-private report. Reference images and judgments are for local inspection only; this bundle cannot be published.</p>', 1)


def export_local_report(value: dict, destination: str | Path, *, media_root: str | Path, packet_roots=None, max_file_bytes=8 * 1024 * 1024, max_total_bytes=MAX_LOCAL_BYTES) -> dict:
    """Copy checked rasters once into a new private directory outside Git."""
    _local_identity(value)
    _validate_text_deliverables(value)
    local = json.loads(json.dumps(value))
    destination = private_directory(destination, must_be_new=True)
    total = 0
    try:
        for item in local.get('text_deliverables', []):
            data = validate_declared_note(item)
            if item.get('packet_path'):
                if not packet_roots or item['review_id'] not in packet_roots:
                    raise ValueError('Local reviewed text packet root is missing')
                checked_file(Path(packet_roots[item['review_id']]), item['packet_path'], expected_hash=item['sha256'], expected_size=item['size'], max_bytes=MAX_NOTE_BYTES)
            name = 'text/' + item['sha256'] + '.txt'
            path = destination / name
            if not path.exists():
                total += len(data)
                if total > max_total_bytes:
                    raise ValueError('Local declared text exceeds the aggregate package byte limit')
                path.parent.mkdir(mode=0o700, exist_ok=True)
                path.write_bytes(data)
                path.chmod(0o600)
            item['export_path'] = name
            item.pop('packet_path', None)
        retained = []
        for item in local.get("media", []):
            root, relative = Path(media_root), item["path"]
            if item.get("root") == "trial":
                trial_id = item["trial_id"]
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", trial_id) or trial_id in {".", ".."}:
                    raise ValueError("Invalid local trial identifier")
                relative = "trials/" + trial_id + "/" + relative
            elif item.get("root") == "packet":
                if not packet_roots or item["review_id"] not in packet_roots:
                    raise ValueError("Local review evidence packet root is missing")
                root = Path(packet_roots[item["review_id"]])
            elif item.get("root") != "run":
                raise ValueError("Local media requires a checked run or packet root")
            _, data = checked_file(root, relative, expected_hash=item["sha256"], expected_size=item.get("size"), max_bytes=max_file_bytes)
            validation = preview_validation(item["path"], data)
            if not validation["allowed"]:
                if item.get("kind") not in {"preview", "review-evidence"}:
                    raise ValueError("Local reference or source proof image failed its content check")
                local.setdefault("withheld_previews", []).append({**{key: item[key] for key in ("name", "case_id", "trial_id", "turn", "sha256", "size", "review_id") if key in item}, "withheld_reason": validation["withheld_reason"]})
                continue
            name = "media/" + item["sha256"] + validation["suffix"]
            path = destination / name
            if not path.exists():
                total += len(data)
                if total > max_total_bytes:
                    raise ValueError("Local report media exceeds the aggregate byte limit")
                path.parent.mkdir(exist_ok=True, mode=0o700)
                path.write_bytes(data)
                path.chmod(0o600)
            item.update(export_path=name, size=len(data), container_check=validation["container_check"])
            item.pop("path", None)
            item.pop("root", None)
            retained.append(item)
        local["media"] = retained
        local.setdefault("coverage", {})["withheld_preview_count"] = len(local.get("withheld_previews", []))
        report._assert_public(local)
        from .changes import validate_report_changes
        validate_report_changes(local)
        local["sanitized"] = True
        local["report_fingerprint"] = canonical_hash({key: value for key, value in local.items() if key != "report_fingerprint"})
        (destination / "report.json").write_text(json.dumps(local, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (destination / "index.html").write_text(render_local_html(local), encoding="utf-8")
        for path in (destination / "report.json", destination / "index.html"):
            path.chmod(0o600)
        checked = validate_local_bundle(destination, max_file_bytes=max_file_bytes, max_total_bytes=max_total_bytes)
        return {**checked, "generation_calls": 0, "visibility": LOCAL_VISIBILITY, "media_bytes": total}
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def validate_local_bundle(root: str | Path, *, max_file_bytes=8 * 1024 * 1024, max_total_bytes=MAX_LOCAL_BYTES) -> dict:
    """Check local data, file hashes and the same trusted report renderer."""
    base = Path(root)
    if base.is_symlink() or stat.S_IMODE(base.stat().st_mode) != 0o700:
        raise ValueError("Local report directory must be private")
    _, raw = checked_file(base, "report.json", max_bytes=max_file_bytes)
    local = json.loads(raw)
    _local_identity(local)
    _validate_text_deliverables(local)
    if local.get("sanitized") is not True:
        raise ValueError("Local report is not sanitized")
    report._assert_public(local)
    expected = {"index.html", "report.json"}
    total = len(raw)
    for item in local.get('text_deliverables', []):
        name = item.get('export_path')
        if name != 'text/' + item['sha256'] + '.txt':
            raise ValueError('Local reviewed text must be content addressed')
        if name not in expected:
            _, data = checked_file(base, name, expected_hash=item['sha256'], expected_size=item['size'], max_bytes=MAX_NOTE_BYTES)
            if data != item['text'].encode('utf-8'):
                raise ValueError('Local reviewed text differs from its displayed content')
            total += len(data)
        expected.add(name)
    for item in local.get("media", []):
        name = item["export_path"]
        if not re.fullmatch(r"media/[0-9a-f]{64}\.(?:png|jpg|webp|gif)", name) or item["sha256"] not in name:
            raise ValueError("Local media must be content addressed")
        if name not in expected:
            _, data = checked_file(base, name, expected_hash=item["sha256"], expected_size=item["size"], max_bytes=max_file_bytes)
            if not preview_validation(name, data)["allowed"]:
                raise ValueError("Local image failed its content check")
            total += len(data)
        expected.add(name)
    _, html_data = checked_file(base, "index.html", max_bytes=max_file_bytes)
    total += len(html_data)
    if total > max_total_bytes:
        raise ValueError("Local report exceeds aggregate byte limit")
    if html_data.decode("utf-8") != render_local_html(local):
        raise ValueError("Local HTML differs from the trusted renderer")
    actual = set()
    for path in base.rglob("*"):
        if path.is_symlink():
            raise ValueError("Local report contains a symbolic link")
        if path.is_file():
            if stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise ValueError("Local report file must be private")
            actual.add(path.relative_to(base).as_posix())
        elif not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise ValueError("Local report contains a nonprivate directory or special file")
    if actual != expected:
        raise ValueError("Local report contains files outside its raster allowlist")
    fingerprint = canonical_hash({key: value for key, value in local.items() if key != "report_fingerprint"})
    if local.get("report_fingerprint") != fingerprint:
        raise ValueError("Local report fingerprint is inconsistent")
    return {"valid": True, "files": len(actual), "bytes": total, "report_fingerprint": fingerprint}
