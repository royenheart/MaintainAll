#!/usr/bin/env python3
"""Detailed normalized report for the legacy art-creation suites, including public media."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard import load_legacy, load_legacy_media, grouped_bars, stacked_bars, line_chart, e, num, badge
from nav import header as site_header


def render() -> str:
    nav_html = site_header('..', (('#quality', 'Quality'), ('#trials', 'Trials'), ('#media', 'Images'), ('#cases', 'Cases'), ('#skills', 'Skill hashes')))
    reports, rows, cases = load_legacy()
    media = load_legacy_media()
    report_titles = {r['id']: r['title'] for r in reports}
    report_ids = [r['id'] for r in reports]

    by = defaultdict(list)
    for row in rows:
        by[(row['report'], row['arm'])].append(row['quality'] or 0)
    report_short = {'formal': 'F', 'refinement-screen-20261013': 'S', 'refinement-retest-20261013': 'R'}
    arm_short = {'previous': 'prev', 'candidate': 'cand', 'none': 'none'}
    labels, values = [], []
    for rid in report_ids:
        for arm in ('previous', 'candidate', 'none'):
            if (rid, arm) in by:
                labels.append(f'{report_short.get(rid, rid[:8])} {arm_short[arm]}')
                values.append(sum(by[(rid, arm)]) / len(by[(rid, arm)]))
    quality_chart = grouped_bars(labels, [('quality', values)], ymax=100)

    counts = {rid: {'pass': 0, 'partial': 0, 'fail': 0, 'unverifiable': 0} for rid in report_ids}
    for row in rows:
        for key in counts[row['report']]:
            counts[row['report']][key] += row[key]
    outcome_chart = stacked_bars([report_titles[x].split()[0] for x in report_ids],
        [(k, [counts[x][k] for x in report_ids]) for k in ('pass', 'partial', 'fail', 'unverifiable')])
    prev = [sum(by.get((x, 'previous'), [0])) / max(1, len(by.get((x, 'previous'), [0]))) for x in report_ids]
    cand = [sum(by.get((x, 'candidate'), [0])) / max(1, len(by.get((x, 'candidate'), [0]))) for x in report_ids]
    trend_chart = line_chart([report_titles[x].split()[0] for x in report_ids], [('previous', prev), ('candidate', cand)])

    case_ids = sorted({r['case'] for r in rows})
    case_by = defaultdict(list)
    for row in rows:
        case_by[(row['case'], row['arm'])].append(row['quality'] or 0)
    def short(c):
        return c.replace('expanded-', '').replace('editorial-transfer', 'editorial').replace('reference-costume', 'costume')[:12]
    case_prev = [sum(case_by.get((c, 'previous'), [0])) / max(1, len(case_by.get((c, 'previous'), [0]))) for c in case_ids]
    case_cand = [sum(case_by.get((c, 'candidate'), [0])) / max(1, len(case_by.get((c, 'candidate'), [0]))) for c in case_ids]
    case_chart = grouped_bars([short(c) for c in case_ids], [('previous', case_prev), ('candidate', case_cand)], ymax=100)

    table = ''.join(
        f'<tr><td><code>{e(r["case"])}</code></td><td>{badge(r["arm"])}</td><td>{e(r["state"])}</td><td>{num(r["quality"] or 0, 1)}%</td>'
        f'<td>{r["pass"]}</td><td>{r["partial"]}</td><td>{r["fail"]}</td><td>{r["unverifiable"]}</td><td>{r["ratings"]}</td><td>{e(r["repeat"])}</td><td>{num(r["seconds"] or 0, 0)}s</td></tr>'
        for r in rows)

    sections = []
    for report in reports:
        rs = [r for r in rows if r['report'] == report['id']]
        sections.append(f'''<section class="panel"><div class="panel-head"><h2>{e(report['title'])}</h2><span class="muted">{e(report['id'])} · {len(rs)} trials · {e(', '.join(report['experiments']))}</span></div>
<div class="panel-body"><div class="table-wrap"><table><thead><tr><th>Experiment</th><th>Case</th><th>Arm</th><th>State</th><th>Quality</th><th>Pass</th><th>Partial</th><th>Fail</th><th>Unverif.</th><th>Model</th><th>Skill</th></tr></thead><tbody>
{''.join(f'<tr><td>{e(r["experiment"])}</td><td><code>{e(r["case"])}</code></td><td>{badge(r["arm"])}</td><td>{e(r["state"])}</td><td>{num(r["quality"] or 0,1)}%</td><td>{r["pass"]}</td><td>{r["partial"]}</td><td>{r["fail"]}</td><td>{r["unverifiable"]}</td><td>{e(r["model"])}</td><td title="{e(r["skill"])}">{e((r["skill"] or "")[:12])}</td></tr>' for r in rs)}
</tbody></table></div></div></section>''')

    def image(m):
        src = 'media/' + Path(m['export']).name
        return f'<a href="{e(src)}" class="shot"><img loading="lazy" src="{e(src)}" alt="{e(m["name"])}"></a>'

    refs = defaultdict(list)
    for m in media:
        if m['kind'] == 'reference':
            refs[m['case']].append(m)
    case_cards = []
    seen = set()
    for c in cases:
        if c['case'] in seen:
            continue
        seen.add(c['case'])
        ref_html = ''.join(f'<figure><a href="media/{e(Path(m["export"]).name)}"><img loading="lazy" src="media/{e(Path(m["export"]).name)}" alt="{e(m["name"])}"></a><figcaption>reference · {e(m["name"])} · {e(m.get("license") or "public")}</figcaption></figure>' for m in refs.get(c['case'], []))
        case_cards.append(f'<details class="case-card"><summary><code>{e(c["case"])}</code> <span class="muted">legacy · {e(c["report_title"])}</span></summary><pre>{e(chr(10).join(c["prompts"])) or "Prompt stored in the legacy bundle."}</pre>{("<div class=refs>" + ref_html + "</div>") if ref_html else ""}</details>')

    all_refs = [m for m in media if m['kind'] == 'reference']
    ref_gallery = ''.join(
        f'<figure><a href="media/{e(Path(m["export"]).name)}"><img loading="lazy" src="media/{e(Path(m["export"]).name)}" alt="{e(m["name"])}"></a><figcaption>{e(m["case"])} · {e(m["name"])} · {e(m.get("license") or "public")}</figcaption></figure>'
        for m in all_refs)
    # pair previous/candidate previews by report, case, turn, artifact name

    groups = defaultdict(dict)
    for m in media:
        if m['kind'] == 'preview' and m['arm'] in ('previous', 'candidate'):
            groups[(m['report'], m['case'], m['turn'], m['name'])][m['arm']] = m
    pairs = []
    for (report, case, turn, name), arms in sorted(groups.items()):
        if 'previous' in arms and 'candidate' in arms:
            pairs.append((report, case, turn, name, arms['previous'], arms['candidate']))
    media_by_report = defaultdict(list)
    for pair in pairs:
        media_by_report[pair[0]].append(pair)
    media_sections = []
    for rid in report_ids:
        if not media_by_report[rid]:
            continue
        opened = ' open' if not media_sections else ''
        blocks = []
        for case in sorted({p[1] for p in media_by_report[rid]}):
            ps = [p for p in media_by_report[rid] if p[1] == case]
            cards = ''.join(
                f'<figure class="compare"><div class="compare-row"><div><span class="arm">previous</span>{image(prev)}</div><div><span class="arm">candidate</span>{image(cand)}</div></div><figcaption>{e(name)} · turn {e(turn)}</figcaption></figure>'
                for _, _, turn, name, prev, cand in ps)
            blocks.append(f'<h4>{e(case)} <span class="muted">· {len(ps)} comparisons</span></h4><div class="compare-grid">{cards}</div>')
        media_sections.append(f'<details class="media-report"{opened}><summary>{e(report_titles[rid])} <span class="muted">{len(media_by_report[rid])} comparisons</span></summary>{"".join(blocks)}</details>')

    skill_rows = ''.join(f'<tr><td>{e(r["report_title"])}</td><td><code>{e(r["case"])}</code></td><td>{badge(r["arm"])}</td><td><code>{e((r["skill"] or "")[:20])}</code></td></tr>' for r in rows)
    style = '''body{margin:0;background:#f6f8fa;color:#1f2328;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;font-variant-numeric:tabular-nums}header{position:sticky;top:0;display:flex;gap:1rem;padding:.6rem 1.5rem;border-bottom:1px solid #d1d9e0;background:#fff}header a{color:#59636e;text-decoration:none;font-size:13px}header nav{display:flex;flex-wrap:wrap;gap:.5rem 1rem}header strong{font-size:13px;letter-spacing:.05em;text-transform:uppercase}main{max-width:1440px;margin:auto;padding:1.2rem 1.5rem 3rem}h1{font-size:22px;margin:.2rem 0}.muted{color:#59636e}.eyebrow{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#59636e}.panel{background:#fff;border:1px solid #d1d9e0;border-radius:8px;margin:1rem 0}.panel-head{display:flex;justify-content:space-between;gap:1rem;padding:.55rem .8rem;border-bottom:1px solid #d1d9e0;background:#f0f3f6}.panel-head h2{font-size:14px;margin:0}.panel-body{padding:.8rem}.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(520px,1fr));gap:1rem}.chart{width:100%;height:auto}.axis{font-size:11px;fill:#59636e}.grid{stroke:#e4e7ec}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #e4e7ec;padding:.4rem .5rem;text-align:left}th{background:#f9fafb;font-size:11px;text-transform:uppercase;color:#59636e}.table-wrap{overflow:auto;border:1px solid #d1d9e0;border-radius:8px}code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}.pill{display:inline-block;border-radius:999px;padding:.05rem .45rem;font-size:11px;font-weight:600}.pill.candidate{background:#ddf4ff;color:#0969da}.pill.previous,.pill.none{background:#eef1f4;color:#59636e}.case-card{border:1px solid #d1d9e0;border-radius:8px;background:#fff;margin:.5rem 0;padding:.4rem .7rem}.case-card summary{cursor:pointer}.case-card pre{white-space:pre-wrap;background:#f6f8fa;border:1px solid #e4e7ec;border-radius:6px;padding:.6rem;font-size:11px}.note{border:1px solid #fedf89;background:#fffaeb;border-radius:8px;padding:.7rem .8rem;margin:1rem 0}.refs{display:flex;flex-wrap:wrap;gap:.8rem}.refs figure,.compare{margin:.3rem;background:#f9fafb;border:1px solid #e4e7ec;border-radius:8px;padding:.4rem}.refs img{height:150px;width:auto;border-radius:4px}.compare-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(480px,1fr));gap:.8rem}.compare-row{display:grid;grid-template-columns:1fr 1fr;gap:.4rem}.compare-row img{width:100%;height:auto;border-radius:4px}.compare .arm{display:block;font-size:10px;text-transform:uppercase;color:#59636e;margin-bottom:.2rem}.compare figcaption{font-size:11px;color:#59636e;padding-top:.3rem}.media-report{border:1px solid #d1d9e0;border-radius:8px;margin:.6rem 0;padding:.6rem}.media-report summary{cursor:pointer;font-weight:600}.media-report h4{font-size:12px;margin:.9rem 0 .4rem}a{color:#0969da}'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Art creation · evaluation</title><style>{style}</style></head><body>
{nav_html}
<main><div class="eyebrow">Legacy suite · normalized</div><h1>Art creation</h1><p class="muted">Legacy art-creation suite: quality = mean verifiable 0/1/2 atom rating; images are the public legacy artifacts.</p>
<div class="note">Candidate vs previous quality is not a controlled attribution result: arms differ by skill version and the rating scale is legacy.</div>
<section class="panel" id="quality"><div class="panel-head"><h2>Quality and outcomes</h2><span class="muted">{len(rows)} trials · {len(reports)} reports</span></div><div class="panel-body"><div class="grid2"><div>{quality_chart}<p class="muted">Mean quality by report and arm.</p></div><div>{outcome_chart}<p class="muted">Atom outcomes: pass=2, partial=1, fail=0, unverifiable excluded.</p></div><div>{trend_chart}<p class="muted">Report-order trend; frozen snapshots, not a time series.</p></div><div>{case_chart}<p class="muted">Per-case mean quality by arm.</p></div></div></div></section>
<section class="panel" id="trials"><div class="panel-head"><h2>Unified trial table</h2><span class="muted">all legacy trials</span></div><div class="panel-body"><div class="table-wrap"><table><thead><tr><th>Case</th><th>Arm</th><th>State</th><th>Quality</th><th>Pass</th><th>Partial</th><th>Fail</th><th>Unverif.</th><th>Ratings</th><th>Repeat</th><th>Duration</th></tr></thead><tbody>{table}</tbody></table></div></div></section>
<section class="panel" id="media"><div class="panel-head"><h2>Images and comparisons</h2><span class="muted">{len(pairs)} previous/candidate pairs · {len(media)} public media</span></div><div class="panel-body"><p class="muted">Input references are shown first; each comparison pairs the same artifact from the previous and candidate arms. The first report is expanded by default.</p><h3>Input references</h3><div class="refs">{ref_gallery or '<p class="muted">No reference images.</p>'}</div><h3>Previous vs candidate</h3>{''.join(media_sections) or '<p class="muted">No paired previews.</p>'}</div></section>
{''.join(sections)}
<section class="panel" id="cases"><div class="panel-head"><h2>Legacy cases, prompts and input images</h2><span class="muted">{len(seen)} cases</span></div><div class="panel-body">{''.join(case_cards)}</div></section>
<section class="panel" id="skills"><div class="panel-head"><h2>Skill hashes</h2><span class="muted">legacy bundles store hashes, not snapshots</span></div><div class="panel-body"><div class="table-wrap"><table><thead><tr><th>Report</th><th>Case</th><th>Arm</th><th>Skill SHA</th></tr></thead><tbody>{skill_rows}</tbody></table></div></div></section>
</main></body></html>'''


def write_page(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    (out / 'index.html').write_text(render())
