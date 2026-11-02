#!/usr/bin/env python3
"""Detail pages for legacy DSH skills that are not in the sealed attribution record set."""
from __future__ import annotations
import html
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from nav import header as site_header

ROOT = Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / 'benchmarks' / 'evaluation' / 'legacy_dsh_summary.json').read_text())


def e(v): return html.escape(str(v if v is not None else ''), quote=True)


def bars(chart):
    labels = chart.get('labels', [])
    withs, withouts = chart.get('with', []), chart.get('without', [])
    width, left, top, bottom = 760, 44, 16, 58
    plot_w, plot_h = width - left - 16, 250 - top - bottom
    group_w = plot_w / max(1, len(labels))
    bar_w = group_w * 0.28
    parts = [f'<svg viewBox="0 0 {width} 250" class="chart">']
    for i in range(5):
        y = top + plot_h - plot_h * i / 4
        parts.append(f'<line x1="{left}" x2="{width-16}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e4e7ec"/><text x="{left-8}" y="{y+4:.1f}" fill="#59636e" font-size="11" text-anchor="end">{25*i}</text>')
    for i, label in enumerate(labels):
        x = left + i * group_w + group_w * 0.18
        for j, (values, color) in enumerate(((withs, '#0969da'), (withouts, '#8250df'))):
            h = plot_h * min(100, values[i] or 0) / 100
            parts.append(f'<rect x="{x + j*bar_w:.1f}" y="{top+plot_h-h:.1f}" width="{bar_w-2:.1f}" height="{h:.1f}" fill="{color}" rx="2"><title>{e(label)}: {values[i]}</title></rect>')
        parts.append(f'<text x="{x + group_w*0.28:.1f}" y="226" fill="#59636e" font-size="11" text-anchor="middle">{e(label)}</text>')
    parts.append(f'<rect x="{left}" y="238" width="10" height="10" fill="#0969da"/><text x="{left+15}" y="247" fill="#59636e" font-size="11">with skill</text><rect x="{left+100}" y="238" width="10" height="10" fill="#8250df"/><text x="{left+115}" y="247" fill="#59636e" font-size="11">without skill</text></svg>')
    return ''.join(parts)


def render(skill):
    rows = ''.join(f'<tr><td>{e(r[0])}</td><td>{e(r[1])}</td><td>{e(r[2])}</td><td>{e(r[3])}</td></tr>' for r in skill['rows'])
    metrics = ''.join(f'<div class="stat"><b>{e(v)}</b><span>{e(k)}</span></div>' for k, v in skill['metrics'])
    nav = site_header('..', (('#comparisons', 'Cases'), ('#source', 'Source')))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(skill['title'])} · evaluation</title><style>
body{{margin:0;background:#f6f8fa;color:#1f2328;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;font-variant-numeric:tabular-nums}}header{{position:sticky;top:0;display:flex;gap:1rem;padding:.6rem 1.5rem;border-bottom:1px solid #d1d9e0;background:#fff}}header a{{color:#59636e;text-decoration:none;font-size:13px}}header strong{{font-size:13px;letter-spacing:.05em;text-transform:uppercase}}main{{max-width:1100px;margin:auto;padding:1.5rem 1.5rem 3rem}}h1{{font-size:24px;margin:.2rem 0}}.eyebrow{{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#59636e}}.muted{{color:#59636e}}.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.6rem;margin:1rem 0}}.stat{{background:#fff;border:1px solid #d1d9e0;border-radius:8px;padding:.65rem .8rem}}.stat b{{display:block;font-size:18px}}.stat span{{font-size:10px;text-transform:uppercase;color:#59636e}}.panel{{background:#fff;border:1px solid #d1d9e0;border-radius:8px;margin:1rem 0}}.panel-head{{display:flex;justify-content:space-between;padding:.55rem .8rem;border-bottom:1px solid #d1d9e0;background:#f0f3f6}}.panel-head h2{{font-size:14px;margin:0}}.panel-body{{padding:.8rem}}.note{{border:1px solid #fedf89;background:#fffaeb;border-radius:8px;padding:.7rem .8rem;margin:1rem 0}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border-bottom:1px solid #e4e7ec;padding:.45rem .55rem;text-align:left}}th{{background:#f9fafb;font-size:11px;text-transform:uppercase;color:#59636e}}.chart{{width:100%;height:auto}}a{{color:#0969da}}code{{font-family:ui-monospace,monospace;font-size:12px}}
</style></head><body>{nav}<main>
<div class="eyebrow">Legacy DSH skill report</div><h1>{e(skill['title'])}</h1><p><strong>{e(skill['status'])}.</strong> {e(skill['summary'])}</p>
<div class="stats">{metrics}</div>
{('<div class="note disabled-note"><strong>Disabled:</strong> ' + e(skill.get('disabled_reason','')) + ' The skill is kept in the repository as <code>SKILL.md.disabled</code>.</div>') if skill.get('disabled') else ''}
<div class="note">{e(skill['caveat'])}</div>
<section class="panel" id="comparisons"><div class="panel-head"><h2>Documented comparisons</h2><span class="muted">legacy evidence, not sealed records</span></div><div class="panel-body"><div class="chart-wrap">{bars(skill['chart'])}</div><div class="table-wrap"><table><thead><tr><th>Case / batch</th><th>With skill</th><th>Without skill</th><th>Reading</th></tr></thead><tbody>{rows}</tbody></table></div></div></section>
<section class="panel" id="source"><div class="panel-head"><h2>Source and limitations</h2></div><div class="panel-body"><p>These numbers come from <code>benchmarks/evaluation/TASK_LEVEL.md</code> and <code>benchmarks/evaluation/FINAL_REPORT.md</code>. Raw trial records were not retained as sealed records in this rebuild; counts here are documented legacy results.</p><p>No cross-skill or cross-model aggregate is computed. The attribution report is the only page in this site backed by the current sealed evidence set.</p></div></section>
</main></body></html>'''


def write_pages(out: Path):
    for skill in DATA['skills']:
        d = out / skill['id']
        d.mkdir(parents=True, exist_ok=True)
        (d / 'index.html').write_text(render(skill))
