"""Independent source reopening and bounded evidence inside the command sandbox."""
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from .contracts import checked_file, content_hash, json_hash
from .grading import _png, _svg


def verifier_identity():
    """Bind the proof to its full trusted implementation, including native drivers."""
    names = ('verifier.py', 'visual_runtime.py', 'browser_driver.py', 'blender_driver.py', 'browser_namespace.py', 'browser_resources.py', 'observation_plans.py')
    return content_hash(json.dumps({name: content_hash(Path(__file__).with_name(name).read_bytes())
                                  for name in names if Path(__file__).with_name(name).is_file()}, sort_keys=True).encode())


def inspect_svg(data):
    """Reject active content, external resources and excessive raster dimensions."""
    root, dimensions = _svg(data)
    if dimensions is None or min(dimensions) <= 0 or max(dimensions) > 8192 or dimensions[0] * dimensions[1] > 16_000_000:
        raise ValueError('Unsupported verifier raster geometry')
    if len(list(root.iter())) > 20000:
        raise ValueError('SVG element ceiling exceeded')
    for node in root.iter():
        if node.tag.split('}')[-1] in {'script', 'foreignObject', 'animate', 'animateTransform', 'set'}:
            raise ValueError('Active SVG is unsupported by the static verifier')
        for key, value in node.attrib.items():
            if key.split('}')[-1] == 'base' or '\\' in value:
                raise ValueError('SVG base overrides and escaped attributes are unsupported')
            if key.split('}')[-1].lower().startswith('on') or '@import' in value.lower():
                raise ValueError('Active SVG attribute')
            if key.split('}')[-1] == 'href' and not (value.startswith('#') or value.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,'))):
                raise ValueError('External SVG resource')
            for resource in re.findall(r'url\s*\(\s*([^)]*)\)', value, re.I):
                if not resource.strip(' \"\'').startswith('#'):
                    raise ValueError('External SVG paint resource')
        if node.tag.split('}')[-1] == 'style':
            text = ''.join(node.itertext())
            if '\\' in text or '@import' in text.lower() or any(not v.strip(' \"\'').startswith('#') for v in re.findall(r'url\s*\(\s*([^)]*)\)', text, re.I)):
                raise ValueError('External or escaped SVG style resource')
    return root, dimensions


def reopen_svg(run_root, trial_id, artifact, renderer, destination):
    """Rebuild actual frozen source; never execute a generated program."""
    from .backends.local_codex import legacy
    trial = Path(run_root) / 'trials' / trial_id
    data = checked_file(trial, artifact['snapshot']).read_bytes()
    if content_hash(data) != artifact['sha256']:
        raise ValueError('Frozen SVG hash mismatch')
    root, dimensions = inspect_svg(data)
    workspace = Path(destination)
    if workspace.exists():
        raise ValueError('Verifier workspace must be new')
    workspace.mkdir(parents=True, mode=0o700)
    (workspace / 'inputs').mkdir()
    (workspace / 'inputs/source.svg').write_bytes(data)
    modified = ET.fromstring(data)
    target = next((n for n in modified.iter() if n.get('fill') and re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?', n.get('fill', ''))), None)
    edit = None
    if target is not None:
        before = target.get('fill')
        after = '#ff00ff' if before.lower() != '#ff00ff' else '#00ff00'
        target.set('fill', after)
        edit = {'attribute': 'fill', 'before': before, 'after': after, 'element': target.tag.split('}')[-1], 'id': target.get('id')}
        (workspace / 'inputs/edited.svg').write_bytes(ET.tostring(modified))
    executable, package = legacy().core.runtime()
    script = "import sys,resource,cairosvg;resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));resource.setrlimit(resource.RLIMIT_CPU,(20,20));cairosvg.svg2png(url=sys.argv[1],write_to=sys.argv[2])"
    values = {}
    for label in ('source', 'edited') if edit else ('source',):
        output = workspace / (label + '.png')
        command = [executable, 'sandbox', '-P', legacy().core.PROFILE, '-C', str(workspace),
                   *legacy().core.config_args(package, renderer=Path(renderer), readonly_inputs=True),
                   str(Path(renderer) / 'bin/python'), '-I', '-c', script,
                   str(workspace / 'inputs' / (label + '.svg')), str(output)]
        process = subprocess.Popen(command, cwd=workspace, env=legacy().core.host_env(), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=25)
        except BaseException:
            legacy().core.stop(process)
            raise
        if process.returncode or not output.is_file() or output.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Sandboxed trusted SVG rebuild failed')
        raster = output.read_bytes()
        _png(raster)
        values[label] = {'path': output.relative_to(run_root).as_posix(), 'sha256': content_hash(raster), 'size': len(raster)}
    changed = edit is not None and values['source']['sha256'] != values['edited']['sha256']
    return {'source_sha256': artifact['sha256'], 'source_reopen_verified': True,
            'source_editability_verified': bool(changed), 'edit_scope': 'one existing fill attribute; no claim about rigging, layout parameters or whole-project editability',
            'edit': edit, 'rendered': values, 'quality_status': 'unassessed', 'generated_code_executed': False,
            'verifier_sha256': verifier_identity()}


def reference_assets(case, through_turn):
    """Return only references supplied by this actual turn, retaining earlier inputs."""
    known = {asset_id for turn in case.get('turns', [])[:through_turn] for asset_id in turn.get('attachments', [])}
    return [asset for asset in case.get('assets', []) if asset['id'] in known]


def reopen_visual(run_root, trial_id, artifact, renderer, destination, tools, *, siblings=(), assets=(), browser_scenario=None, browser_plan=None):
    """Reopen frozen HTML/native files; no solver-generated Python is executed."""
    from .visual_runtime import stage, sandbox
    root = Path(run_root)
    trial = root / 'trials' / trial_id
    data = checked_file(trial, artifact['snapshot']).read_bytes()
    if content_hash(data) != artifact['sha256']:
        raise ValueError('Frozen visual source hash mismatch')
    workspace = Path(destination)
    if workspace.exists():
        raise ValueError('Verifier workspace must be new')
    workspace.mkdir(parents=True, mode=0o700)
    inputs = workspace / 'inputs'
    inputs.mkdir()
    stage(workspace, tools)
    # Browser resources remain data inside the offline namespace. Generated
    # Python and solver evidence never become verifier programs or scenarios.
    fmt = artifact['format']
    allowed = {'.html', '.htm', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico', '.avif',
               '.css', '.js', '.mjs', '.json', '.txt', '.woff', '.woff2', '.ttf', '.otf',
               '.mp4', '.webm', '.wav', '.mp3', '.ogg', '.glb', '.gltf', '.bin'} if fmt == 'html' else {'.blend', '.png', '.jpg', '.jpeg', '.webp', '.glb', '.gltf'}
    total = 0
    copied = set()
    for item in (artifact, *siblings):
        if Path(item['path']).suffix.lower() not in allowed or item['path'] in copied:
            continue
        rel = Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts or '\\' in item['path']:
            raise ValueError('Unsafe local visual resource path')
        target = inputs / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = checked_file(trial, item['snapshot']).read_bytes()
        if len(raw) > 8 * 1024 * 1024 or content_hash(raw) != item['sha256']:
            raise ValueError('Frozen local resource hash mismatch')
        total += len(raw)
        if total > 32 * 1024 * 1024:
            raise ValueError('Frozen visual resource set exceeds its byte limit')
        target.write_bytes(raw)
        copied.add(item['path'])
    for item in assets:
        source = checked_file(root, item['path'])
        raw = source.read_bytes()
        if content_hash(raw) != item['sha256']:
            raise ValueError('Frozen visual reference hash mismatch')
        total += len(raw)
        if total > 32 * 1024 * 1024:
            raise ValueError('Frozen visual resource set exceeds its byte limit')
        target = inputs / 'inputs' / (item['id'] + source.suffix.lower())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    source = inputs / artifact['path']
    if fmt == 'html':
        if 'browser' not in tools:
            raise ValueError('Independent browser runtime is unavailable')
        from .browser_namespace import namespace_capture
        if browser_plan is None:
            namespace_capture(workspace, source, workspace / 'captures', tools, spec=browser_scenario, timeout=60)
        else:
            if browser_plan['source_artifact'] != artifact['path']:
                raise ValueError('Frozen observation plan belongs to a different source artifact')
            capture_root = workspace / 'captures'
            capture_root.mkdir(mode=0o700)
            trace_enabled = any('trace_samples_ms' in scenario['spec'] for scenario in browser_plan['scenarios'])
            merged = {'schema_version': 4 if trace_enabled else 3, 'source_sha256': artifact['sha256'],
                      'scope': 'case-bound sampled actions and conditions; not full continuity, application FFT or aesthetic quality',
                      'passed': True, 'source_reopen_verified': True, 'frames': [], 'actions': [],
                      'input_events': [], 'audio_samples': [], 'action_snapshots': [], 'dom_samples': [], 'trace_samples': [], 'scenarios': []}
            for scenario in browser_plan['scenarios']:
                identifier = scenario['id']
                result = namespace_capture(workspace, source, capture_root / identifier, tools,
                                           spec=scenario['spec'], timeout=60, exclude_top_level=('captures',))
                merged['passed'] &= result.get('passed') is True
                merged['source_reopen_verified'] &= result.get('source_reopen_verified') is True
                merged['scenarios'].append({'id': identifier, 'spec_sha256': json_hash(scenario['spec']),
                    'source_reopen_verified': result.get('source_reopen_verified') is True,
                    'scope_version': result.get('scope_version'),
                    'audio_probe': result.get('audio_probe'),
                    'resource_boundary': {key: value for key, value in result.get('namespace', {}).get('resource_boundary', {}).items()
                                          if key in {'method', 'passed', 'limits', 'observations', 'child_returncode'}}})
                for frame in result.get('frames', []):
                    merged['frames'].append({**frame, 'path': identifier + '/' + frame['path'],
                                             'label': identifier + ' / ' + frame['label'], 'scenario': identifier})
                for key in ('actions', 'input_events', 'audio_samples', 'action_snapshots', 'dom_samples', 'trace_samples'):
                    merged[key].extend({**row, 'scenario': identifier} for row in result.get(key, []))
            (capture_root / 'evidence.json').write_text(json.dumps(merged, indent=2, allow_nan=False) + '\n')
    elif fmt == 'blend':
        if 'blender' not in tools:
            raise ValueError('Independent Blender runtime is unavailable')
        sandbox(workspace, renderer, tools, [tools['blender']['executable'], '--background', '--factory-startup',
                '--disable-autoexec', '--threads', '1', '--python', 'tools/blender_driver.py', '--',
                '--source', str(source), '--output', 'captures'], timeout=120)
    else:
        raise ValueError('Unsupported visual source format')
    evidence = json.loads((workspace / 'captures/evidence.json').read_text())
    if evidence.get('source_sha256') != artifact['sha256']:
        raise ValueError('Visual proof source identity mismatch')
    rendered = {}
    if fmt == 'html':
        images = [('frame-' + str(i + 1), row) for i, row in enumerate(evidence.get('frames', []))]
    else:
        images = list(evidence.get('rendered', {}).items())
    for label, item in images:
        target = Path(item['path'])
        if not target.is_absolute():
            target = workspace / 'captures' / target
        if not target.is_relative_to(workspace / 'captures'):
            raise ValueError('Visual proof image escapes its new workspace')
        raw = checked_file(workspace, target.relative_to(workspace).as_posix()).read_bytes()
        _png(raw)
        if len(raw) > 8 * 1024 * 1024 or content_hash(raw) != item['sha256']:
            raise ValueError('Visual proof image inventory mismatch')
        rendered[label] = {'path': target.relative_to(root).as_posix(), 'sha256': content_hash(raw), 'size': len(raw),
                           **{key: item[key] for key in ('profile', 'time_ms', 'capture_started_ms', 'capture_completed_ms', 'requested_time_ms', 'viewport', 'label') if key in item}}
    if not rendered:
        raise ValueError('Independent visual capture produced no raster evidence')
    proof = {'source_sha256': artifact['sha256'], 'format': fmt,
             'source_reopen_verified': evidence.get('passed') is True and evidence.get('source_reopen_verified') is True if fmt == 'html' else evidence.get('source_reopen_verified') is True,
             'source_editability_verified': evidence.get('source_editability_verified') is True if fmt == 'blend' else False,
             'scope': evidence.get('scope', evidence.get('edit_scope', 'bounded native source inspection')),
             'rendered': rendered, 'edit': evidence.get('edit'), 'quality_status': 'unassessed',
             'generated_code_executed': fmt == 'html', 'execution_scope': 'sandboxed-html' if fmt == 'html' else 'native-autoexec-disabled',
             'verifier_sha256': verifier_identity()}
    if fmt == 'html':
        proof['playback'] = {'scope': 'independently sampled browser playback; no full continuity or preference score',
                             'interactions': evidence.get('interactions') is True,
                             'samples': [{key: frame[key] for key in ('profile', 'time_ms', 'capture_started_ms', 'capture_completed_ms', 'requested_time_ms', 'viewport', 'label') if key in frame}
                                         for frame in evidence.get('frames', [])]}
        if browser_plan is not None:
            proof['playback'].update(scope=evidence['scope'], observation_plan_sha256=json_hash(browser_plan),
                                     scope_version=evidence['schema_version'], scenarios=evidence['scenarios'],
                                     actions=evidence['actions'], input_events=evidence['input_events'],
                                     audio_samples=evidence['audio_samples'],
                                     action_snapshots=evidence['action_snapshots'], dom_samples=evidence['dom_samples'],
                                     trace_samples=evidence['trace_samples'],
                                     interactions=any(e.get('isTrusted') is True for e in evidence['input_events']))
    if fmt == 'blend' and evidence.get('modified_native'):
        native = evidence['modified_native']
        path = workspace / 'captures' / native['path']
        raw = checked_file(workspace, path.relative_to(workspace).as_posix()).read_bytes()
        if len(raw) > 8 * 1024 * 1024 or content_hash(raw) != native['sha256'] or len(raw) != native['size']:
            raise ValueError('Modified native scene inventory mismatch')
        proof['modified_native'] = {**native, 'path': path.relative_to(root).as_posix()}
    # Seal detailed traces separately; callers may review these independently.
    trace = workspace / 'captures/evidence.json'
    proof['trace'] = {'path': trace.relative_to(root).as_posix(), 'sha256': content_hash(trace.read_bytes()), 'size': trace.stat().st_size}
    return proof
