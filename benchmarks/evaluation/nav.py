"""Shared top navigation for generated evaluation pages.

Each detail page gets a link back to the index and links to its own sections only.
The index page is the only place that links across reports.
"""
from __future__ import annotations
import html


def header(prefix: str = '', items: tuple[tuple[str, str], ...] = ()) -> str:
    prefix = prefix.rstrip('/') + '/' if prefix not in ('', '.') else ''
    links = [(prefix + 'index.html', 'All skills')]
    links.extend(items)
    nav = ''.join(f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>' for href, label in links)
    return ('<header><strong>MaintainAll / Evaluation</strong>'
            f'<nav style="display:flex;flex-wrap:wrap;gap:.5rem 1rem">{nav}</nav></header>')
