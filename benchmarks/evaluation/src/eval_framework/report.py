"""One static report for every suite. Minimal by design; legacy renderers remain adapters."""
from __future__ import annotations

from pathlib import Path
import html
import json
import shutil

from .contracts import sha256


def _escape(value) -> str:
    return html.escape(str(value if value is not None else ''), quote=True)


def _record_row(record) -> str:
    manifest = record.manifest
    best = None
    for attempt in record.attempts:
        if attempt.reward is not None and attempt.max_reward:
            best = attempt.reward / attempt.max_reward
            break
    score = '—' if best is None else f'{best:.3f}'
    metrics = record.metrics or {}
    coverage = metrics.get('scored', 0) / metrics.get('attempts', 1) if metrics.get('attempts') else 0
    return ('<tr>'
            f'<td>{_escape(manifest.suite)}</td><td>{_escape(manifest.case)}</td>'
            f'<td>{_escape(manifest.split)}</td><td>{_escape(manifest.arm)}</td><td>{_escape(record.state)}</td>'
            f'<td>{score}</td><td>{_escape(metrics.get("scored"))}/{_escape(metrics.get("attempts"))}</td>'
            f'<td>{coverage:.0%}</td><td>{_escape(manifest.model)}</td>'
            f'<td title="{_escape(manifest.workflow_sha256)}">{_escape(manifest.workflow_sha256[:12])}</td>'
            f'<td title="{_escape(record.record_hash)}">{_escape(record.record_hash[:12])}</td>'
            '</tr>')


def build_site(records, published, output: Path, catalog_path: Path | None = None) -> dict:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    data_dir = output / 'records'
    data_dir.mkdir(exist_ok=True)
    for record in records:
        target = data_dir / f'{record.record_id}.json'
        target.write_text(json.dumps(record.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    suites = sorted({record.manifest.suite for record in records})
    rows = '\n'.join(_record_row(record) for record in records)
    reports = '\n'.join(
        f'<li><a href="{_escape(item.get("package_url") or "#")}">{_escape(item.get("title"))}</a> '
        f'<span class="muted">({_escape(item.get("suite_title"))}; legacy report)</span></li>'
        for item in published)
    body = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unified evaluation</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#17202a}}
h1{{margin-bottom:.2rem}} .muted{{color:#667085}} table{{border-collapse:collapse;width:100%;margin:1rem 0}}
th,td{{border-bottom:1px solid #e4e7ec;padding:.45rem .5rem;text-align:left;vertical-align:top}}
th{{background:#f9fafb}} code{{font-family:ui-monospace,monospace}} .note{{background:#fffaeb;border:1px solid #fedf89;padding:.8rem;border-radius:8px}}
</style></head><body>
<h1>Unified evaluation</h1>
<p class="muted">One report surface for the dsh skill suite and published legacy suites. Records are immutable projections; adapters do not rewrite source evidence.</p>
<div class="note"><strong>Scope:</strong> this page combines sealed attribution records with the published art-creation suites. Rich art-creation pages remain on their legacy renderer; the attribution summary below is a separate two-metric view. Missing or invalid attempts are not zero-quality evidence.</div>
<h2>Suites</h2>
<p>{_escape(', '.join(suites)) if suites else 'No records ingested yet.'}</p>
<h2>Records</h2>
<table><thead><tr><th>Suite</th><th>Case</th><th>Split</th><th>Arm</th><th>State</th><th>Score</th><th>Scored/attempts</th><th>Coverage</th><th>Model</th><th>Workflow</th><th>Record</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>Published legacy reports</h2>
<ul>{reports or '<li class="muted">None in the catalog.</li>'}</ul>
<h2>Artifacts</h2>
<p>The machine-readable records are in <code>records/</code>; this page is generated with zero model calls.</p>
</body></html>'''
    (output / 'index.html').write_text(body)
    catalog = {
        'schema_version': 2,
        'suites': [{'id': 'dsh-skills', 'title': 'DSH skills'}] + [
            {'id': item['suite'], 'title': item.get('suite_title') or item['suite']}
            for item in published if item.get('suite') and item.get('suite') != 'dsh-skills'
        ],
        'reports': published,
        'records': [{'id': record.record_id, 'suite': record.manifest.suite,
                     'case': record.manifest.case, 'split': record.manifest.split,
                     'state': record.state, 'record_hash': record.record_hash} for record in records],
    }
    (output / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    manifest = {
        'schema': 1, 'records': len(records), 'suites': suites, 'catalog_sha256': sha256(catalog_path.read_bytes()) if catalog_path and catalog_path.is_file() else None,
        'record_hashes': sorted(record.record_hash for record in records),
        'catalog_sha256': sha256(catalog_path.read_bytes()) if catalog_path and catalog_path.is_file() else None,
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    return manifest
