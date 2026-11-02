"""Adapter: the existing public skill_bench catalog.

The unified page lists the published reports; their rich report renderer remains the
source for their own pages until the unified renderer reaches parity.
"""
from __future__ import annotations

from pathlib import Path
import json


def catalog(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        return {'schema_version': 1, 'suites': [], 'reports': []}
    data = json.loads(path.read_text())
    if not isinstance(data.get('suites'), list) or not isinstance(data.get('reports'), list):
        raise ValueError('invalid skill_bench catalog')
    return data


def published(path: Path) -> list[dict]:
    data = catalog(path)
    suites = {entry['id']: entry for entry in data.get('suites', [])}
    items = []
    for report in data.get('reports', []):
        suite = suites.get(report.get('suite_id'), {})
        items.append({
            'id': report.get('id'), 'title': report.get('title'), 'suite': report.get('suite_id'),
            'suite_title': suite.get('title', report.get('suite_id')), 'path': report.get('path'),
            'package_url': (report.get('package') or {}).get('url'),
            'summary': report.get('summary') or {},
        })
    return items
