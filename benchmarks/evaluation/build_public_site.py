#!/usr/bin/env python3
"""Build the unified static evaluation site: framework page + attribution section + art-creation legacy site."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'public-benchmark-site'
SITE = ROOT / 'benchmarks' / 'evaluation' / 'site'
MEDIA_ROOT = ROOT / 'benchmarks' / 'evaluation' / 'art-media'
LEGACY_DATA = ROOT / 'benchmarks' / 'evaluation' / 'legacy_art_data.json'


def run(cmd, **kw):
    print('+', ' '.join(str(x) for x in cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True, **kw)


def copy_art_media(art_dir: Path) -> int:
    data = json.loads(LEGACY_DATA.read_text())
    target = art_dir / 'media'
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for media in data.get('media', []):
        export = str(media.get('export') or '')
        if not export.startswith('media/') or '..' in Path(export).parts:
            continue
        source = MEDIA_ROOT / media['report'] / Path(export).name
        if not source.is_file():
            continue
        destination = target / Path(export).name
        if destination.exists():
            continue
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)
        copied += 1
    return copied


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    run([sys.executable, '-m', 'eval_framework.cli', 'ingest-agent-eval'],
        env={**__import__('os').environ, 'PYTHONPATH': str(ROOT / 'benchmarks' / 'evaluation' / 'src')})
    run([sys.executable, '-m', 'eval_framework.cli', 'build-site'],
        env={**__import__('os').environ, 'PYTHONPATH': str(ROOT / 'benchmarks' / 'evaluation' / 'src')})
    OUT.mkdir(parents=True)
    skill_dir = OUT / 'dsh-sandbox-attribution'
    skill_dir.mkdir()
    for item in SITE.iterdir():
        if item.name == 'index.html':
            continue
        target = skill_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    shutil.copy2(ROOT / 'benchmarks' / 'evaluation' / 'METRICS_ATTRIBUTION.md', skill_dir / 'METRICS_ATTRIBUTION.md')
    shutil.copy2(ROOT / 'benchmarks' / 'evaluation' / 'PREREGISTRATION_ATTRIBUTION.md', skill_dir / 'PREREGISTRATION_ATTRIBUTION.md')
    sys.path.insert(0, str(ROOT / 'benchmarks' / 'evaluation'))
    from dashboard import render
    from overview import render as render_overview
    from legacy_dsh import write_pages as write_legacy_dsh
    (skill_dir / 'index.html').write_text(render(SITE / 'records', base='..', include_legacy=False))
    write_legacy_dsh(OUT)
    (OUT / 'index.html').write_text(render_overview(SITE / 'records'))
    # public machine-readable catalogs at the site root
    for name in ('catalog.json', 'manifest.json'):
        if (SITE / name).is_file():
            shutil.copy2(SITE / name, OUT / name)
    art_dir = OUT / 'art-creation'
    art_dir.mkdir()
    copied_media = copy_art_media(art_dir)
    from legacy_dashboard import write_page as write_legacy_page
    write_legacy_page(art_dir)
    (OUT / '.nojekyll').write_text('')
    print(f'built {OUT} ({sum(1 for _ in OUT.rglob("*") if _.is_file())} files, {copied_media} media)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
