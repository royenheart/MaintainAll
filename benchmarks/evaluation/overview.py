#!/usr/bin/env python3
"""Landing page indexing the evaluated skills and their detailed reports."""
from __future__ import annotations
import html
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard import load_legacy, pct, num
from nav import header as site_header

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / 'benchmarks' / 'evaluation' / 'attribution_summary.json'
DATASET = ROOT / 'benchmarks' / 'agent_eval' / 'datasets' / 'validation-1.json'
LEGACY_DSH = ROOT / 'benchmarks' / 'evaluation' / 'legacy_dsh_summary.json'


def e(v): return html.escape(str(v if v is not None else ''), quote=True)


def render(records_dir: Path) -> str:
    summary = json.loads(SUMMARY.read_text())
    b_n = b_e = a_n = a_e = b_s = a_s = 0
    for case in summary['cases']:
        if case['truth'] not in ('both', 'dsh'):
            continue
        for arm in case['arms']:
            if arm['arm'] == 'B':
                b_n += arm['valid_n']
                b_e += arm['evidence']
                b_s += arm['semantic'] or 0
            if arm['arm'] == 'A0':
                a_n += arm['valid_n']
                a_e += arm['evidence']
                a_s += arm['semantic'] or 0
    records = list(Path(records_dir).glob('*.json'))
    reports, rows, cases = load_legacy()
    candidate = [r['quality'] or 0 for r in rows if r['arm'] == 'candidate']
    previous = [r['quality'] or 0 for r in rows if r['arm'] == 'previous']
    cand = sum(candidate) / len(candidate) if candidate else 0
    prev = sum(previous) / len(previous) if previous else 0
    legacy_dsh = json.loads(LEGACY_DSH.read_text())['skills']
    extra_cards = ''.join(
        f'<section class="card"><div class="meta"><span class="tag">Legacy DSH skill</span>{("<span class=\"tag disabled\">disabled</span>" if s.get("disabled") else "")}<span class="tag">{e(s["status"])}</span></div><h3>{e(s["title"])}</h3><p class="muted">{e(s["summary"])}</p><div class="metrics">' +
        ''.join(f'<div><b>{e(v)}</b><span>{e(k)}</span></div>' for k, v in s['metrics'][:3]) +
        f'</div><div class="meta"><span>documented legacy evidence</span></div><a class="button alt" href="{e(s["id"])}/index.html">Open legacy report →</a></section>' for s in legacy_dsh)
    extra_rows = ''.join(
        f'<tr><td>dsh-skills</td><td><a href="{e(s["id"])}/index.html">{e(s["title"])}</a></td><td>legacy documented</td><td>{"disabled" if s.get("disabled") else e(s["status"])}</td><td><a href="{e(s["id"])}/index.html">{e(s["id"])}/</a></td></tr>' for s in legacy_dsh)
    dataset = json.loads(DATASET.read_text())
    case_count = len(dataset.get('cases', [])) + len(dataset.get('holdout', []))

    nav = site_header('', ())
    style = '''
:root{--canvas:#f6f8fa;--surface:#fff;--soft:#f0f3f6;--fg:#1f2328;--muted:#59636e;--line:#d1d9e0;--accent:#0969da;--pass:#1a7f37;--part:#9a6700;--fail:#cf222e;--radius:8px}
*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--fg);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;font-variant-numeric:tabular-nums}
header{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;gap:.5rem 1.2rem;align-items:baseline;padding:.6rem 1.5rem;border-bottom:1px solid var(--line);background:rgba(255,255,255,.96);backdrop-filter:blur(8px)}
header strong{font-size:13px;letter-spacing:.05em;text-transform:uppercase}header a{color:var(--muted);text-decoration:none;font-size:13px}header a:hover{color:var(--fg)}
main{max-width:1100px;margin:0 auto;padding:2.4rem 1.5rem 3rem}h1{font-size:30px;letter-spacing:-.03em;margin:.2rem 0 .5rem}h2{font-size:15px;margin:1.6rem 0 .6rem}.eyebrow{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.muted{color:var(--muted)}p{max-width:78ch}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem;margin:1.2rem 0}.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:1rem 1.1rem;display:flex;flex-direction:column;gap:.5rem}.card h3{font-size:17px;margin:0}.card .meta{display:flex;flex-wrap:wrap;gap:.35rem .6rem;font-size:11px;color:var(--muted)}.tag{border:1px solid var(--line);border-radius:999px;padding:.05rem .45rem;background:var(--soft);color:var(--fg)}.tag.disabled{background:#ffebe9;color:#cf222e;border-color:#ffcecb}
.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.4rem;margin:.2rem 0}.metrics b{display:block;font-size:18px;line-height:1.2}.metrics span{font-size:10px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.card a.button{display:inline-block;margin-top:auto;background:var(--accent);color:#fff;text-decoration:none;border-radius:6px;padding:.35rem .6rem;font-weight:600;font-size:13px;width:max-content}.card a.button.alt{background:var(--surface);color:var(--accent);border:1px solid var(--accent)}
table{border-collapse:collapse;width:100%;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;font-size:13px}th,td{padding:.55rem .65rem;border-bottom:1px solid #e4e7ec;text-align:left;vertical-align:top}th{background:var(--soft);font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}a{color:var(--accent);text-underline-offset:2px}code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}.note{border:1px solid #fedf89;background:#fffaeb;border-radius:var(--radius);padding:.7rem .8rem;margin:1rem 0}
@media(max-width:700px){main{padding:1.2rem}.metrics{grid-template-columns:1fr 1fr}}
'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Evaluation index · MaintainAll</title><style>{style}</style></head><body>
{nav}
<main><div class="eyebrow">Benchmark index</div><h1>Evaluated skills</h1><p>Each report is separate; the evidence level is labelled per card, and scores from different suites are never combined.</p>
<div class="cards">
<section class="card"><div class="meta"><span class="tag">DSH skill</span><span class="tag">runtime / sandbox</span><span class="tag">frozen</span></div><h3>DSH sandbox attribution</h3><p class="muted">Does a skill make the agent name the sandbox layer that hid a GPU or <code>/dev</code> object, and cite verifiable evidence?</p>
<div class="metrics"><div><b>{pct(b_e, b_n)}</b><span>B evidence</span></div><div><b>{pct(a_e, a_n)}</b><span>A0 evidence</span></div><div><b>{pct(b_s, b_n)}</b><span>B semantic</span></div></div>
<div class="meta"><span>{len(records)} sealed records</span><span>{case_count} dataset cases</span><span>case11 / case09 / case08</span></div>
<a class="button" href="dsh-sandbox-attribution/index.html">Open detailed report →</a></section>
<section class="card"><div class="meta"><span class="tag">Legacy suite</span><span class="tag">art creation</span><span class="tag">published</span></div><h3>Art creation</h3><p class="muted">Artifact quality of art-creation skill arms, with previous/candidate comparisons and original case evidence.</p>
<div class="metrics"><div><b>{num(prev,1)}%</b><span>previous quality</span></div><div><b>{num(cand,1)}%</b><span>candidate quality</span></div><div><b>{len(rows)}</b><span>trials</span></div></div>
<div class="meta"><span>{len(reports)} reports</span><span>{len(cases)} case contexts</span><span>legacy atom scale</span></div>
<a class="button" href="art-creation/index.html">Open detailed report →</a></section>
{extra_cards}</div>
<div class="note"><strong>Scales:</strong> DSH = semantic + evidence; art/legacy DSH = native legacy scales. Not comparable.</div>
<h2>All reports</h2>
<table><thead><tr><th>Suite</th><th>Report</th><th>Records / trials</th><th>Primary result</th><th>Link</th></tr></thead><tbody>
<tr><td>dsh-skills</td><td>Sandbox attribution</td><td>{len(records)} sealed records</td><td>B evidence {pct(b_e, b_n)}; A0 {pct(a_e, a_n)}</td><td><a href="dsh-sandbox-attribution/index.html">dsh-sandbox-attribution/</a></td></tr>
<tr><td>art-creation</td><td>Art creation</td><td>{len(rows)} legacy trials / {len(reports)} reports</td><td>candidate {num(cand,1)}% vs previous {num(prev,1)}% quality</td><td><a href="art-creation/index.html">art-creation/</a></td></tr>
{extra_rows}
</tbody></table>
<p class="muted" style="margin-top:1.5rem">Generated from sealed records and public legacy bundles; no model calls. Source: <code>benchmarks/evaluation/</code>.</p>
</main></body></html>'''
