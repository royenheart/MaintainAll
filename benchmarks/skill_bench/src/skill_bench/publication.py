"""Check and stage explicitly catalogued public reports with zero generation."""
from __future__ import annotations

import html
import base64
import json
from pathlib import Path
import re
import shutil
import tempfile

from .report import validate_public_bundle, merge_reports, render_html, _assert_public
from .review import checked_file, preview_validation
from .review import canonical_hash

DEFAULT_REPORTS = '.cache/skill-bench/reports'
MAX_REPORTS = 128
MAX_COLLECTION_BYTES = 256 * 1024 * 1024
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}')
SUITE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')


def _title(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 160 or any(ord(c) < 32 for c in value):
        raise ValueError('Benchmark titles must be short, plain text')


def _suites(entries, *, published=False):
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_REPORTS:
        raise ValueError('A catalog requires one to 128 benchmark suites')
    ids, paths = set(), set()
    for entry in entries:
        fields = {'id', 'title', 'path'} if published else {'id', 'title'}
        if not isinstance(entry, dict) or set(entry) != fields:
            raise ValueError('Invalid benchmark suite fields')
        if not isinstance(entry['id'], str) or not SUITE_NAME.fullmatch(entry['id']) or entry['id'] in ids:
            raise ValueError('Benchmark suite identities must be safe and unique')
        _title(entry['title'])
        ids.add(entry['id'])
        if published:
            if not isinstance(entry['path'], str) or not NAME.fullmatch(entry['path']) or entry['path'] in paths:
                raise ValueError('Unsafe or duplicate benchmark suite path')
            paths.add(entry['path'])
    return entries


def combine_public_reports(directories):
    """Union verified experiment records and their original raster evidence.

    A report may already contain history. Experiment/trial identities prevent
    double-counting when its original bundle is also listed in the catalog.
    Conflicting execution records fail rather than replacing earlier evidence.
    """
    experiments, contexts, cohorts, roots = {}, {}, {}, {}
    trials, ratings, pairs, media = {}, {}, {}, {}
    last = None
    def retain(mapping, key, item, label):
        if key in mapping and mapping[key] != item:
            raise ValueError('Conflicting public ' + label + ' identity')
        mapping[key] = item
    def original_id(value, experiment):
        prefix = experiment + '/'
        return value[len(prefix):] if value.startswith(prefix) else value
    for directory in directories:
        checked = validate_public_bundle(directory)
        _, raw = checked_file(directory, 'report.json', max_bytes=8 * 1024 * 1024)
        source = json.loads(raw)
        identity = checked['report_fingerprint']
        if source['report_fingerprint'] != identity:
            raise ValueError('Public report changed during history assembly')
        roots[identity] = Path(directory)
        last = source
        for item in source.get('experiments', []):
            retain(experiments, item['id'], item, 'experiment')
        for item in source.get('case_contexts', []):
            retain(contexts, item['case_fingerprint'], item, 'case context')
        for item in source['cohorts']:
            retain(cohorts, item['id'], item, 'cohort')
        for row in source['trials']:
            exp = row.get('experiment', source['experiment'])
            item = {k: v for k, v in row.items() if k != 'experiment'}
            item['id'] = original_id(row['id'], exp)
            retain(trials, (exp, item['id']), item, 'trial')
        for field, mapping in (('ratings', ratings), ('pairs', pairs)):
            for row in source[field]:
                exp = row.get('experiment', source['experiment'])
                item = {k: v for k, v in row.items() if k != 'experiment'}
                for key in ('trial_id', 'left_trial_id', 'right_trial_id'):
                    if key in item:
                        item[key] = original_id(item[key], exp)
                observed = {'score', 'reason', 'evidence'} if field == 'ratings' else {'outcome_for_left', 'reason', 'evidence'}
                key = (exp, canonical_hash({k: v for k, v in item.items() if k not in observed}))
                retain(mapping, key, item, field[:-1])
        for row in source.get('media', []):
            exp = row.get('experiment', source['experiment'])
            item = dict(row)
            if 'trial_id' in item:
                item['trial_id'] = exp + '/' + original_id(item['trial_id'], exp)
            item['experiment'] = exp
            key = canonical_hash(item)
            item.update(path=item.pop('export_path'), root='public', _public_bundle=identity)
            media[key] = item
    if last is None:
        raise ValueError('At least one public report is required')
    parts = []
    for exp, metadata in experiments.items():
        part = {**last, 'experiment': exp, 'current_experiment': exp, 'experiments': [metadata],
            'case_contexts': list(contexts.values()), 'cohorts': list(cohorts.values()),
            'trials': [row for (e, _), row in trials.items() if e == exp],
            'ratings': [row for (e, _), row in ratings.items() if e == exp],
            'pairs': [row for (e, _), row in pairs.items() if e == exp],
            'media': [], 'history': [], 'dimensions': []}
        part.pop('report_fingerprint', None)
        parts.append(part)
    combined = merge_reports(parts)
    combined['current_experiment'] = list(experiments)[-1]
    combined['media'] = list(media.values())
    combined['historical_media_omitted'] = 0
    combined['limitations'] = [text for text in combined.get('limitations', [])
        if not text.startswith('Historical media remains')]
    combined['limitations'].append('Only manually submitted evaluations appear. Missing commits and unevaluated commits have no quality point.')
    combined['report_fingerprint'] = canonical_hash({k: v for k, v in combined.items() if k != 'report_fingerprint'})
    return combined, roots


def portable_report(root, output, *, suite_id=None, max_bytes=96 * 1024 * 1024, source_max_bytes=64 * 1024 * 1024):
    """Produce one checked HTML with original rasters embedded for app previews."""
    from .report_view import render_document
    shared = (Path(root) / 'publication.json').is_file()
    if shared:
        validate_public_site(root)
        _, manifest_raw = checked_file(root, 'publication.json', max_bytes=64 * 1024)
        suites = json.loads(manifest_raw)['suites']
        if suite_id is None and len(suites) > 1:
            raise ValueError('Choose a benchmark suite for a portable multi-suite site export')
        selected = next((s for s in suites if suite_id is None or s['id'] == suite_id), None)
        if selected is None:
            raise ValueError('Portable export refers to an unknown benchmark suite')
        report_path = selected['path'] + '/report.json'
    else:
        if suite_id is not None:
            raise ValueError('Suite selection requires a published benchmark site')
        validate_public_bundle(root, max_total_bytes=source_max_bytes)
        report_path = 'report.json'
    destination = Path(output).absolute()
    if '..' in destination.parts or any(p.is_symlink() for p in (destination, *destination.parents)):
        raise ValueError('Portable destination cannot contain traversal or links')
    if destination.exists():
        raise ValueError('Portable report destination must be new')
    _, raw = checked_file(root, report_path, max_bytes=8 * 1024 * 1024)
    public = json.loads(raw)
    embedded = {}
    encoded_bytes = 0
    for item in public.get('media', []):
        name = item['export_path']
        if name in embedded:
            continue
        relative = name.removeprefix('../') if shared else name
        _, data = checked_file(root, relative, expected_hash=item['sha256'], expected_size=item['size'], max_bytes=8 * 1024 * 1024)
        suffix = Path(name).suffix.lower()
        kind = {'.png': 'png', '.jpg': 'jpeg', '.webp': 'webp', '.gif': 'gif'}[suffix]
        embedded[name] = 'data:image/' + kind + ';base64,' + base64.b64encode(data).decode('ascii')
        encoded_bytes += len(embedded[name]) + len(name)
        if encoded_bytes > max_bytes:
            raise ValueError('Portable report exceeds its byte ceiling; use the directory report')
    document = render_document(public, embedded_media=embedded).encode('utf-8')
    if len(document) > max_bytes:
        raise ValueError('Portable report exceeds its byte ceiling; use the directory report')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(document)
    return {'generation_calls': 0, 'images': len(embedded), 'bytes': len(document),
        'report_fingerprint': public['report_fingerprint']}


def _ordinary_directory(path):
    target = Path(path).absolute()
    if '..' in target.parts or any(part.is_symlink() for part in (target, *target.parents)):
        raise ValueError('Public report paths cannot contain parent traversal or symbolic links')
    if not target.is_dir():
        raise ValueError('Public report collection directory is missing')
    return target


def _unique_object(pairs):
    answer = {}
    for key, value in pairs:
        if key in answer:
            raise ValueError('Duplicate public catalog field')
        answer[key] = value
    return answer


def _catalog(root):
    base = _ordinary_directory(root)
    _, raw = checked_file(base, 'reports.json', max_bytes=64 * 1024)
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] not in (1, 2):
        raise ValueError('Public catalog requires schema_version 1 or 2')
    version = value['schema_version']
    if set(value) != ({'schema_version', 'reports'} if version == 1 else {'schema_version', 'suites', 'reports'}):
        raise ValueError('Invalid public catalog fields')
    suites = _suites(value['suites']) if version == 2 else [{'id': 'default', 'title': 'Skill evaluation'}]
    suite_ids = {s['id'] for s in suites}
    entries = value['reports']
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_REPORTS:
        raise ValueError('Public catalog requires one to 128 reports')
    identities, paths = set(), set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != ({'id', 'title', 'path'} if version == 1 else {'id', 'title', 'path', 'suite_id'}):
            raise ValueError('Catalog reports require id, title, path and a suite assignment in version 2')
        if any(not isinstance(entry[field], str) or not NAME.fullmatch(entry[field]) for field in ('id', 'path')):
            raise ValueError('Catalog identity and path must be safe single directory names')
        if entry['path'] in {'.', '..'} or entry['id'] in identities or entry['path'] in paths:
            raise ValueError('Catalog report identities and paths must be unique')
        _title(entry['title'])
        if version == 2 and (not isinstance(entry['suite_id'], str) or entry['suite_id'] not in suite_ids):
            raise ValueError('Catalog report refers to an unknown benchmark suite')
        _ordinary_directory(base / entry['path'])
        identities.add(entry['id'])
        paths.add(entry['path'])
    normalized = {**value, 'suites': suites, 'reports': [dict(e, suite_id=e.get('suite_id', 'default')) for e in entries]}
    if {e['suite_id'] for e in normalized['reports']} != suite_ids:
        raise ValueError('Register a benchmark suite with at least one submitted report')
    return base, normalized


def validate_collection(root):
    """Validate only listed bundles; unrelated root files are never published."""
    base, catalog = _catalog(root)
    bundles, total = [], 0
    for entry in catalog['reports']:
        checked = validate_public_bundle(base / entry['path'])
        total += checked['bytes']
        if total > MAX_COLLECTION_BYTES:
            raise ValueError('Public report collection exceeds the aggregate byte ceiling')
        bundles.append({**entry, **checked})
    return {'valid': True, 'reports': len(bundles), 'suites': len(catalog['suites']), 'suite_entries': catalog['suites'], 'bytes': total,
            'generation_calls': 0, 'bundles': bundles}


def _landing_page(entries, suites):
    tabs = ''.join('<a href="' + suite['path'] + '/index.html">' + html.escape(suite['title']) + '</a>' for suite in suites)
    groups = []
    for number, suite in enumerate(suites, 1):
        groups.append('<section><h2>' + str(number) + '. <a href="' + suite['path'] + '/index.html">' + html.escape(suite['title'])
            + '</a></h2><p>Evaluations, version comparisons and original case evidence in one report.</p></section>')
    return ('<!doctype html><html lang="en" translate="no"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;">'
        '<title>Skill evaluation reports</title><style>'
        'body{margin:0;background:#f5f4ed;color:#141413;font:15px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}'
        'main{max-width:1100px;margin:auto;padding:28px 24px}h1{font-weight:600;font-size:27px;line-height:1.2}'
        'a{color:#1B365D;text-underline-offset:.2em}ul{list-style:none;padding:0}li{padding:8px 0}'
        'section{border-top:1px solid #d5d1c4;padding:16px 0}h2{font-weight:600}p{color:#6b6a64}'
        'nav{display:flex;flex-wrap:wrap;gap:16px 24px;margin:18px 0;padding:10px 0;border-block:1px solid #d5d1c4}'
        '*{box-sizing:border-box}body{overflow-wrap:anywhere}@media(max-width:600px){main{padding:28px 18px}h1{font-size:29px}}'
        '</style></head><body><main><p>MAINTAINALL / SKILL BENCHMARK</p>'
        '<h1>Skill benchmark suites</h1><nav aria-label="Benchmark suites">' + tabs + '</nav><p>Evaluations are started manually on a local machine. '
        'CI checks the submitted public files and prepares this report collection; it does not run models or add quality ratings.</p>'
        '<p>Open the complete site directory in a browser, or serve its root locally. '
        'An isolated HTML preview cannot access adjacent image files. Images are stored once in assets/; embedding is an optional export.</p>'
        + ''.join(groups) + '<p>Each suite keeps its own experiments, commit history and requirement ratings. '
        'Results from different suites are never combined into a score or trend. Changed evaluation conditions remain separate within a suite.</p></main></body></html>')


def _navigation(entry, entries, suites):
    suite = next(s for s in suites if s['id'] == entry['suite_id'])
    return {'suite': {k: suite[k] for k in ('id', 'title')}, 'suites': suites,
        'reports': [{k:e[k] for k in ('id', 'title', 'path')} for e in entries if e['suite_id'] == suite['id']],
        'current_path': entry['path']}


def _site_projection(report, *, source_fingerprint=None, navigation=None):
    public = json.loads(json.dumps(report))
    for item in public.get('media', []):
        original = item.pop('path', item.get('export_path'))
        if not isinstance(original, str) or not re.fullmatch(r'media/[0-9a-f]{64}\.(?:png|jpg|webp|gif)', original):
            raise ValueError('Shared image projection requires a checked content-addressed path')
        item['export_path'] = '../assets/' + original.removeprefix('media/')
        for key in ('root', '_public_bundle', '_source_trial_id'):
            item.pop(key, None)
    for row in public.get('ratings', []) + public.get('pairs', []):
        for evidence in row.get('evidence', []):
            if 'public_path' in evidence:
                path = evidence['public_path']
                if not re.fullmatch(r'media/[0-9a-f]{64}\.png', path):
                    raise ValueError('Public derivative evidence requires a checked image path')
                evidence['public_path'] = '../assets/' + path.removeprefix('media/')
    public['asset_layout'] = 'shared-site-v1'
    public['sanitized'] = True
    if navigation is not None:
        public['publication'] = navigation
    if source_fingerprint:
        public['source_report_fingerprint'] = source_fingerprint
    _assert_public(public)
    public['report_fingerprint'] = canonical_hash({k:v for k,v in public.items() if k != 'report_fingerprint'})
    return public


def _write_site_report(public, target):
    target.mkdir()
    (target/'report.json').write_text(json.dumps(public, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    (target/'index.html').write_text(render_html(public), encoding='utf-8')


def validate_public_site(root):
    """Check a shared-asset site without running its HTML or relaxing bundle checks."""
    base = _ordinary_directory(root)
    _, raw = checked_file(base, 'publication.json', max_bytes=64*1024)
    manifest = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(manifest, dict) or set(manifest) != {'schema_version','kind','generation_calls','reports','suites'} or type(manifest['schema_version']) is not int or manifest['schema_version'] != 2 or manifest['kind'] != 'skill-benchmark-site' or type(manifest['generation_calls']) is not int or manifest['generation_calls'] != 0:
        raise ValueError('Invalid shared report site manifest')
    suites = _suites(manifest['suites'], published=True)
    suite_ids = {s['id'] for s in suites}
    entries = manifest['reports']
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_REPORTS:
        raise ValueError('Shared site requires one report per benchmark suite')
    expected = {'publication.json','index.html'}
    identities, paths, media = set(), set(), {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'id','title','path','report_fingerprint','suite_id','role'}:
            raise ValueError('Invalid shared report site entry')
        for field in ('id','path'):
            if not isinstance(entry[field], str) or not NAME.fullmatch(entry[field]) or entry[field] in {'.','..'}:
                raise ValueError('Unsafe shared report path or identity')
        if entry['id'] in identities or entry['path'] in paths:
            raise ValueError('Duplicate shared report site identity')
        identities.add(entry['id']); paths.add(entry['path'])
        _title(entry['title'])
        if not isinstance(entry['suite_id'], str) or entry['suite_id'] not in suite_ids or entry['role'] != 'history':
            raise ValueError('Invalid shared report suite or role')
        if not isinstance(entry['report_fingerprint'], str) or not re.fullmatch(r'[0-9a-f]{64}', entry['report_fingerprint']):
            raise ValueError('Invalid shared report fingerprint')
        prefix = entry['path']+'/'
        _, data = checked_file(base, prefix+'report.json', max_bytes=8*1024*1024)
        public = json.loads(data, object_pairs_hook=_unique_object)
        if public.get('schema_version') != 1 or public.get('kind') != 'skill-benchmark-report' or public.get('sanitized') is not True or public.get('asset_layout') != 'shared-site-v1':
            raise ValueError('Shared site contains an invalid public report')
        _assert_public(public)
        from .changes import validate_report_changes
        validate_report_changes(public)
        if public.get('publication') != _navigation(entry, entries, suites):
            raise ValueError('Shared report suite navigation differs from the site catalog')
        fingerprint = canonical_hash({k:v for k,v in public.items() if k != 'report_fingerprint'})
        if public.get('report_fingerprint') != fingerprint or fingerprint != entry['report_fingerprint']:
            raise ValueError('Shared report fingerprint mismatch')
        _, document = checked_file(base, prefix+'index.html', max_bytes=8*1024*1024)
        if document.decode('utf-8') != render_html(public):
            raise ValueError('Shared report HTML differs from the trusted escaped renderer')
        expected.update({prefix+'report.json',prefix+'index.html'})
        for item in public.get('media', []):
            from .public_media import validate_derivation, strip_png_metadata
            validate_derivation(item)
            name = item.get('export_path', '')
            match = re.fullmatch(r'\.\./assets/([0-9a-f]{64})\.(png|jpg|webp|gif)', name)
            if not match or match[1] != item.get('sha256') or item.get('privacy') != 'public' or type(item.get('size')) is not int or item['size'] < 1:
                raise ValueError('Shared media requires an ordinary hash-addressed public image')
            asset = name.removeprefix('../')
            identity = (item['sha256'],item['size'])
            if asset in media and media[asset] != identity:
                raise ValueError('Conflicting shared image identity')
            if asset not in media:
                _, image = checked_file(base, asset, expected_hash=item['sha256'], expected_size=item['size'], max_bytes=8*1024*1024)
                if not preview_validation(asset,image)['allowed']:
                    raise ValueError('Shared image failed its content check')
                if asset.endswith('.png') and strip_png_metadata(image)[1]:
                    raise ValueError('Public PNG metadata must be removed before publication')
            media[asset] = identity
            expected.add(asset)
    for suite in suites:
        history = [e for e in entries if e['suite_id'] == suite['id'] and e['role'] == 'history']
        if len(history) != 1 or history[0]['path'] != suite['path']:
            raise ValueError('Each benchmark suite requires exactly one independent history')
    _, landing = checked_file(base, 'index.html', max_bytes=64*1024)
    if landing.decode('utf-8') != _landing_page(entries, suites):
        raise ValueError('Shared site landing page differs from its trusted renderer')
    actual, total = set(), 0
    for path in base.rglob('*'):
        if path.is_symlink():
            raise ValueError('Shared report site contains a symbolic link')
        if path.is_file():
            actual.add(path.relative_to(base).as_posix())
            total += path.stat().st_size
        elif not path.is_dir():
            raise ValueError('Shared report site contains a special file')
    if actual != expected:
        raise ValueError('Shared report site contains files outside its public allowlist')
    if total > MAX_COLLECTION_BYTES:
        raise ValueError('Shared report site exceeds its aggregate byte ceiling')
    return {'valid':True,'suites':len(suites),'files':len(actual),'bytes':total,'shared_media_files':len(media),
        'shared_media_bytes':sum(size for _,size in media.values()),'generation_calls':0}


def publish_collection(root, output):
    """Stage a new site with one original image per hash, never embedding by default."""
    checked = validate_collection(root)
    base, destination = Path(root).absolute(), Path(output).absolute()
    if '..' in destination.parts or any(part.is_symlink() for part in (destination, *destination.parents)):
        raise ValueError('Publication destination cannot contain traversal or links')
    if destination.exists():
        raise ValueError('Publication requires a new output directory')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.skill-report-', dir=destination.parent))
    try:
        (staging/'assets').mkdir()
        suites = [dict(s, path='timeline' if i == 0 else 'suite-' + s['id']) for i,s in enumerate(checked['suite_entries'])]
        histories = [{'id':'suite-' + s['id'], 'title':s['title'], 'path':s['path'],
            'suite_id':s['id'], 'role':'history'} for s in suites]
        reserved = {h[k] for h in histories for k in ('id', 'path')}
        if any(entry[k] in reserved for entry in checked['bundles'] for k in ('id', 'path')):
            raise ValueError('Benchmark history paths and identities are reserved')
        entries = histories
        for entry in checked['bundles']:
            source = base/entry['path']
            _, raw = checked_file(source, 'report.json', max_bytes=8 * 1024 * 1024)
            public = json.loads(raw)
            if public['report_fingerprint'] != entry['report_fingerprint']:
                raise ValueError('Public report changed during publication')
            for item in public.get('media', []):
                _, data = checked_file(source,item['export_path'],expected_hash=item['sha256'],expected_size=item['size'],max_bytes=8*1024*1024)
                target = staging/'assets'/Path(item['export_path']).name
                if not target.exists():
                    target.write_bytes(data)
        for history in histories:
            selected = [e for e in checked['bundles'] if e['suite_id'] == history['suite_id']]
            combined, roots = combine_public_reports([base/e['path'] for e in selected])
            if set(roots) != {e['report_fingerprint'] for e in selected}:
                raise ValueError('Public report changed during benchmark history assembly')
            projection = _site_projection(combined,navigation=_navigation(history, entries, suites))
            _write_site_report(projection,staging/history['path'])
            history['report_fingerprint'] = projection['report_fingerprint']
        manifest = {'schema_version':2,'kind':'skill-benchmark-site','generation_calls':0,'reports':entries,'suites':suites}
        (staging/'publication.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
        (staging/'index.html').write_text(_landing_page(entries, suites),encoding='utf-8')
        checked['site'] = validate_public_site(staging)
        checked['layout'] = 'shared-assets'
        checked['embedded_images'] = False
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return checked
