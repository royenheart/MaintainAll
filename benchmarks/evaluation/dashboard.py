#!/usr/bin/env python3
"""Build the public unified evaluation page from sealed records and legacy art-creation bundles."""
from __future__ import annotations
import html
import json
from collections import Counter, defaultdict
from nav import header as site_header
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'benchmarks' / 'results' / 'catalog.json'
ART_ROOT = ROOT / 'docs' / 'research' / 'skill-benchmark-architecture-2026-10-09' / 'outputs'
SUMMARY = ROOT / 'benchmarks' / 'evaluation' / 'attribution_summary.json'
CASES = ROOT / 'benchmarks' / 'agent_eval' / 'cases'
CONTROLS = ROOT / 'benchmarks' / 'evaluation' / 'controls'
SKILL = ROOT / 'skills' / 'dsh-sandbox-attribution' / 'SKILL.md'
DATASET = ROOT / 'benchmarks' / 'agent_eval' / 'datasets' / 'validation-1.json'
LEGACY_DATA = ROOT / 'benchmarks' / 'evaluation' / 'legacy_art_data.json'

COLORS = {'B': '#0969da', 'A0': '#8c959f', 'candidate': '#0969da', 'previous': '#8250df', 'none': '#8c959f',
          'pass': '#1a7f37', 'partial': '#9a6700', 'fail': '#cf222e', 'unverifiable': '#8c959f'}


def e(value) -> str:
    return html.escape(str(value if value is not None else ''), quote=True)


def num(value, digits=1):
    return '—' if value is None else f'{value:.{digits}f}'


def pct(value, total):
    return '—' if value is None or not total else f'{value}/{total} ({100 * value / total:.0f}%)'


def load_records(records_dir):
    out = []
    for path in sorted(Path(records_dir).glob('*.json')):
        data = json.loads(path.read_text())
        m = data.get('manifest') or {}
        attempts = data.get('attempts') or []
        attempt = attempts[0] if attempts else {}
        checks = attempt.get('checks') or {}
        arm = {'with': 'B', 'without': 'A0'}.get(m.get('arm'), m.get('arm'))
        out.append({'id': data.get('record_id'), 'suite': m.get('suite'), 'case': m.get('case'),
                    'split': m.get('split'), 'arm': arm, 'state': data.get('state'),
                    'score': attempt.get('reward'), 'max': attempt.get('max_reward'),
                    'checks': checks, 'model': m.get('model'), 'skill': m.get('skill_sha256') or (m.get('environment') or {}).get('baseline_skill_sha256'),
                    'workflow': m.get('workflow_sha256'), 'usage': attempt.get('usage') or {},
                    'trial': attempt.get('trial_id'), 'record_hash': data.get('record_hash'),
                    'error': attempt.get('error')})
    return out


def load_legacy():
    if LEGACY_DATA.is_file():
        data = json.loads(LEGACY_DATA.read_text())
        return data['reports'], data['rows'], data['cases']
    catalog = json.loads(CATALOG.read_text())
    rows, cases, reports = [], [], []
    for item in catalog.get('reports', []):
        path = ART_ROOT / item['path'] / 'report.json'
        if not path.is_file():
            continue
        data = json.loads(path.read_text())
        ratings = defaultdict(list)
        for rating in data.get('ratings', []):
            ratings[rating.get('trial_id')].append(rating)
        report = {'id': item['id'], 'title': item.get('title'), 'suite': item.get('suite_id'),
                  'trials': len(data.get('trials', [])), 'ratings': len(data.get('ratings', [])),
                  'pairs': len(data.get('pairs', [])), 'cases': len(data.get('case_contexts', [])),
                  'experiments': [x.get('id') if isinstance(x, dict) else str(x) for x in data.get('experiments', [])], 'limitations': data.get('limitations', [])}
        reports.append(report)
        for trial in data.get('trials', []):
            rs = ratings.get(trial.get('id'), [])
            numeric = [r for r in rs if isinstance(r.get('score'), int)]
            counts = Counter(r.get('score') for r in rs)
            quality = (sum(r['score'] for r in numeric) / (2 * len(numeric)) * 100) if numeric else None
            usage = trial.get('usage') or {}
            rows.append({
                'report': item['id'], 'report_title': item.get('title'), 'experiment': trial.get('experiment') or data.get('experiment'),
                'case': trial.get('case_id'), 'arm': trial.get('arm'), 'state': trial.get('status'), 'repeat': trial.get('repeat'),
                'quality': quality, 'ratings': len(rs), 'numeric': len(numeric),
                'pass': counts.get(2, 0), 'partial': counts.get(1, 0), 'fail': counts.get(0, 0),
                'unverifiable': counts.get('unverifiable', 0), 'model': trial.get('model'),
                'skill': trial.get('skill_hash'), 'seconds': trial.get('seconds'), 'tokens': usage.get('input_tokens'),
                'output_tokens': usage.get('output_tokens'), 'cohort': trial.get('cohort_id'),
            })
        for context in data.get('case_contexts', []):
            prompts = []
            for turn in context.get('turns', []):
                prompt = turn.get('prompt')
                if prompt and prompt not in prompts:
                    prompts.append(prompt)
            cases.append({'report': item['id'], 'report_title': item.get('title'), 'case': context.get('case_id'),
                          'fingerprint': context.get('case_fingerprint'), 'prompts': prompts,
                          'turns': len(context.get('turns', []))})
    return reports, rows, cases


def load_report_json(report_id):
    return json.loads((ART_ROOT / report_id / 'report.json').read_text())


def load_dataset():
    data = json.loads(DATASET.read_text())
    entries = list(data.get('cases', [])) + [{**x, 'split': 'holdout'} for x in data.get('holdout', [])]
    for entry in entries:
        case_dir = CASES / entry['id']
        entry['prompt'] = (case_dir / 'prompts' / 'task.txt').read_text() if (case_dir / 'prompts' / 'task.txt').is_file() else ''
        truth = ROOT / 'benchmarks' / 'agent_eval' / 'truth' / f"{entry['id']}.json"
        entry['truth'] = truth.read_text() if truth.is_file() else ''
        cfg = case_dir / 'case.json'
        entry['case_json'] = cfg.read_text() if cfg.is_file() else ''
    return data, entries


def diff_html(left: str, right: str) -> str:
    import difflib
    lines = list(difflib.unified_diff(left.splitlines(), right.splitlines(), fromfile='baseline', tofile='candidate', lineterm=''))
    out, old, new = [], 0, 0
    for line in lines:
        cls = 'ctx'
        if line.startswith('@@'):
            cls = 'hunk'
        elif line.startswith('+'):
            cls, new = 'add', new + 1
        elif line.startswith('-'):
            cls, old = 'del', old + 1
        elif line.startswith(('---', '+++')):
            cls = 'meta'
        out.append(f'<div class="diff-line {cls}"><span class="ln">{old if cls != "add" else ""}</span><span class="ln">{new if cls != "del" else ""}</span><code>{e(line)}</code></div>')
    return '<div class="diff">' + ''.join(out) + '</div>'


def grouped_bars(groups, series, *, height=250, ymax=100):
    width, left, top, bottom = 760, 44, 16, 58
    plot_w, plot_h = width - left - 16, height - top - bottom
    group_w = plot_w / max(1, len(groups))
    bar_w = group_w * 0.72 / max(1, len(series))
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">']
    for i in range(5):
        y = top + plot_h - plot_h * i / 4
        parts.append(f'<line x1="{left}" x2="{width-16}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/><text x="{left-8}" y="{y+4:.1f}" class="axis" text-anchor="end">{ymax*i/4:.0f}</text>')
    for gi, group in enumerate(groups):
        gx = left + gi * group_w + group_w * 0.14
        for si, (name, values) in enumerate(series):
            value = values[gi] or 0
            h = plot_h * min(value, ymax) / ymax
            x = gx + si * bar_w
            parts.append(f'<rect x="{x:.1f}" y="{top+plot_h-h:.1f}" width="{bar_w-2:.1f}" height="{h:.1f}" fill="{COLORS.get(name, "#0969da")}" rx="2"><title>{e(name)}: {value:.1f}</title></rect>')
        parts.append(f'<text x="{gx + group_w*0.36:.1f}" y="{height-32}" class="axis" text-anchor="middle">{e(group)}</text>')
    # legend
    lx = left
    for name, _ in series:
        parts.append(f'<rect x="{lx}" y="{height-22}" width="10" height="10" rx="2" fill="{COLORS.get(name, "#0969da")}"/><text x="{lx+15}" y="{height-13}" class="axis">{e(name)}</text>')
        lx += 24 + 8 * len(name)
    parts.append('</svg>')
    return ''.join(parts)


def line_chart(labels, series, *, height=250, ymax=100):
    width, left, top, bottom = 760, 44, 16, 58
    plot_w, plot_h = width - left - 16, height - top - bottom
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">']
    for i in range(5):
        y = top + plot_h - plot_h * i / 4
        parts.append(f'<line x1="{left}" x2="{width-16}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/><text x="{left-8}" y="{y+4:.1f}" class="axis" text-anchor="end">{ymax*i/4:.0f}</text>')
    step = plot_w / max(1, len(labels))
    for name, values in series:
        pts = []
        for i, value in enumerate(values):
            x = left + step * (i + 0.5)
            y = top + plot_h - plot_h * min(value or 0, ymax) / ymax
            pts.append(f'{x:.1f},{y:.1f}')
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{COLORS.get(name, "#0969da")}"><title>{e(name)} {labels[i]}: {value:.1f}</title></circle>')
        parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{COLORS.get(name, "#0969da")}" stroke-width="2"/>')
    for i, label in enumerate(labels):
        x = left + step * (i + 0.5)
        parts.append(f'<text x="{x:.1f}" y="{height-32}" class="axis" text-anchor="middle">{e(label)}</text>')
    lx = left
    for name, _ in series:
        parts.append(f'<rect x="{lx}" y="{height-22}" width="10" height="10" rx="2" fill="{COLORS.get(name, "#0969da")}"/><text x="{lx+15}" y="{height-13}" class="axis">{e(name)}</text>')
        lx += 24 + 8 * len(name)
    parts.append('</svg>')
    return ''.join(parts)


def stacked_bars(labels, series, *, height=250):
    width, left, top, bottom = 760, 44, 16, 58
    plot_w, plot_h = width - left - 16, height - top - bottom
    totals = [sum(values[i] for _, values in series) for i in range(len(labels))]
    ymax = max(totals) or 1
    group_w = plot_w / max(1, len(labels))
    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">']
    for gi, label in enumerate(labels):
        x = left + gi * group_w + group_w * 0.2
        y = top + plot_h
        for name, values in series:
            h = plot_h * values[gi] / ymax
            y -= h
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{group_w*0.6:.1f}" height="{h:.1f}" fill="{COLORS.get(name, "#8c959f")}"><title>{e(name)}: {values[gi]}</title></rect>')
        parts.append(f'<text x="{x + group_w*0.3:.1f}" y="{height-32}" class="axis" text-anchor="middle">{e(label)}</text>')
    lx = left
    for name, _ in series:
        parts.append(f'<rect x="{lx}" y="{height-22}" width="10" height="10" rx="2" fill="{COLORS.get(name, "#8c959f")}"/><text x="{lx+15}" y="{height-13}" class="axis">{e(name)}</text>')
        lx += 24 + 8 * len(name)
    parts.append('</svg>')
    return ''.join(parts)


def badge(value):
    return f'<span class="pill {e(value)}">{e(value)}</span>'


def render(records_dir: Path, base: str = '.', include_legacy: bool = True) -> str:
    prefix = '' if base == '.' else base.rstrip('/') + '/'
    legacy_class = '' if include_legacy else 'legacy-only'
    body_class = '' if include_legacy else 'dsh-only'
    nav_html = site_header(prefix, (('#attribution', 'Attribution'), ('#cases', 'Cases & datasets'), ('#skill', 'Skill diff'), ('#records', 'Records')))
    records = load_records(records_dir)
    summary = json.loads(SUMMARY.read_text())
    legacy_reports, legacy_rows, legacy_cases = load_legacy()
    dataset, dataset_entries = load_dataset()
    skill_text = SKILL.read_text()
    controls = {name: (CONTROLS / name / 'SKILL.md').read_text() for name in ('minimal-probe', 'sham-label') if (CONTROLS / name / 'SKILL.md').is_file()}
    import hashlib
    skill_hash = hashlib.sha256(SKILL.read_bytes()).hexdigest()

    # --- attribution aggregates ---
    attr_cases = summary['cases']
    attr_total = {'B': 0, 'A0': 0}
    attr_evidence = {'B': 0, 'A0': 0}
    attr_semantic = {'B': 0, 'A0': 0}
    case_labels, semantic_vals, evidence_vals = [], [], []
    for case in attr_cases:
        for arm in case['arms']:
            case_labels.append(f"{case['case'].split('-')[-1]} {arm['arm']}")
            semantic_vals.append(100 * (arm['semantic'] or 0) / max(1, arm['valid_n']))
            evidence_vals.append(100 * arm['evidence'] / max(1, arm['valid_n']))
            if case['truth'] in ('both', 'dsh'):
                attr_total[arm['arm']] += arm['valid_n']
                attr_evidence[arm['arm']] += arm['evidence']
                attr_semantic[arm['arm']] += arm['semantic'] or 0
    attr_chart = grouped_bars(case_labels, [('semantic', semantic_vals), ('evidence', evidence_vals)])

    # record-level chart (sealed records by case/arm, evidence pass = 1)
    by_case_arm = defaultdict(list)
    for r in records:
        by_case_arm[(r['case'], r['arm'])].append(1 if (r['checks'] or {}).get('passed') else 0)
    rec_labels = [f"{case.split('-')[-1]} {arm}" for (case, arm) in sorted(by_case_arm)]
    rec_vals = [100 * sum(by_case_arm[key]) / len(by_case_arm[key]) for key in sorted(by_case_arm)]
    record_chart = grouped_bars(rec_labels, [('evidence', rec_vals)], ymax=100)

    # --- legacy aggregates ---
    report_titles = {r['id']: r['title'] for r in legacy_reports}
    report_ids = [r['id'] for r in legacy_reports]
    quality_by = defaultdict(list)
    rating_counts = defaultdict(Counter)
    for row in legacy_rows:
        quality_by[(row['report'], row['arm'])].append(row['quality'] or 0)
        rating_counts[row['report']]['pass'] += row['pass']
        rating_counts[row['report']]['partial'] += row['partial']
        rating_counts[row['report']]['fail'] += row['fail']
        rating_counts[row['report']]['unverifiable'] += row['unverifiable']
    leg_labels = [f"{report_titles[x].split()[0]} {arm}" for x in report_ids for arm in ('previous', 'candidate') if (x, arm) in quality_by]
    leg_vals = [sum(quality_by[(x, arm)]) / len(quality_by[(x, arm)]) for x in report_ids for arm in ('previous', 'candidate') if (x, arm) in quality_by]
    legacy_quality_chart = grouped_bars(leg_labels, [('quality', leg_vals)], ymax=100)
    legacy_cases_ids = sorted({r['case'] for r in legacy_rows})
    by_case_arm = defaultdict(list)
    for row in legacy_rows:
        by_case_arm[(row['case'], row['arm'])].append(row['quality'] or 0)
    case_prev = [sum(by_case_arm.get((c, 'previous'), [0])) / max(1, len(by_case_arm.get((c, 'previous'), [0]))) for c in legacy_cases_ids]
    case_cand = [sum(by_case_arm.get((c, 'candidate'), [0])) / max(1, len(by_case_arm.get((c, 'candidate'), [0]))) for c in legacy_cases_ids]
    legacy_case_chart = grouped_bars(legacy_cases_ids, [('previous', case_prev), ('candidate', case_cand)], ymax=100)
    outcome_chart = stacked_bars([report_titles[x].split()[0] for x in report_ids], [
        ('pass', [rating_counts[x]['pass'] for x in report_ids]),
        ('partial', [rating_counts[x]['partial'] for x in report_ids]),
        ('fail', [rating_counts[x]['fail'] for x in report_ids]),
        ('unverifiable', [rating_counts[x]['unverifiable'] for x in report_ids])])
    prev_vals = [sum(quality_by.get((x, 'previous'), [0])) / max(1, len(quality_by.get((x, 'previous'), [0]))) for x in report_ids]
    cand_vals = [sum(quality_by.get((x, 'candidate'), [0])) / max(1, len(quality_by.get((x, 'candidate'), [0]))) for x in report_ids]
    legacy_trend_chart = line_chart([report_titles[x].split()[0] for x in report_ids],
                                    [('previous', prev_vals), ('candidate', cand_vals)])

    # --- attribution record table ---
    rec_rows = []
    for r in records:
        checks = r['checks'] or {}
        failed = [k for k, v in checks.items() if v is False and k != 'passed']
        rec_rows.append('<tr>'
            f'<td>{e(r["suite"])}</td><td><code>{e(r["case"])}</code></td><td>{e(r["split"])}</td><td>{badge(r["arm"])}</td>'
            f'<td>{e(r["state"])}</td><td>{num((r["score"] or 0) * 100, 0)}%</td>'
            f'<td>{e("pass" if checks.get("passed") else "fail")}</td><td class="mono">{e(", ".join(failed) or "—")}</td><td>{e(r["model"])}</td>'
            f'<td title="{e(r["skill"])}">{e((r["skill"] or "")[:12])}</td>'
            f'<td><a href="records/{e(r["id"])}.json"><code>{e((r["record_hash"] or "")[:12])}</code></a></td></tr>')
    # --- legacy table ---
    leg_rows = []
    for row in legacy_rows:
        score = None if row['quality'] is None else row['quality'] / 100
        leg_rows.append('<tr data-report="{report}" data-arm="{arm}">'
            f'<td>art-creation</td><td><code>{e(row["case"])}</code></td><td>legacy</td><td>{badge(row["arm"])}</td>'
            f'<td>{e(row["state"])}</td><td>{num((score or 0) * 100, 0)}%</td>'
            f'<td>{e(row["numeric"])}/{e(row["ratings"])}</td>'
            f'<td>{e(row["model"])}</td><td title="{e(row["skill"])}">{e((row["skill"] or "")[:12])}</td>'
            f'<td>{num(row["seconds"] or 0, 0)}s</td><td>{e(row["report_title"])}</td></tr>'.format(**{'report': row['report'], 'arm': row['arm']}))
    # --- legacy report sections ---
    report_sections = []
    for report in legacy_reports:
        rows = [r for r in legacy_rows if r['report'] == report['id']]
        cases = sorted({r['case'] for r in rows})
        model = sorted({r['model'] for r in rows if r['model']})
        report_sections.append(f'''<section class="panel {legacy_class}">
<div class="panel-head"><h2>{e(report['title'])}</h2><span class="muted">{e(report['id'])} · {len(rows)} trials · {len(cases)} cases</span></div>
<div class="panel-body"><p class="muted">Experiment(s): {e(', '.join(report['experiments']) or '—')}; models: {e(', '.join(model) or '—')}. Legacy ratings use a 0/1/2 atom scale; quality is the mean over verifiable atoms, not a reward.</p>
<div class="table-wrap table-scroll"><table><thead><tr><th>Case</th><th>Arm</th><th>State</th><th>Quality</th><th>Pass</th><th>Partial</th><th>Fail</th><th>Unverif.</th><th>Ratings</th><th>Repeat</th></tr></thead><tbody>
''')
        for r in rows:
            report_sections.append(f'<tr><td><code>{e(r["case"])}</code></td><td>{badge(r["arm"])}</td><td>{e(r["state"])}</td><td>{num(r["quality"] or 0, 1)}%</td><td>{r["pass"]}</td><td>{r["partial"]}</td><td>{r["fail"]}</td><td>{r["unverifiable"]}</td><td>{r["ratings"]}</td><td>{e(r["repeat"])}</td></tr>')
        report_sections.append('</tbody></table></div></div></section>')
    # --- dataset table + active case cards ---
    dataset_rows = ''.join(
        f'<tr data-status="{e(x.get("status",""))}" data-split="{e(x.get("split",""))}">'
        f'<td><code>{e(x["id"])}</code></td><td>{e(x.get("split",""))}</td><td>{e(x.get("status",""))}</td>'
        f'<td>{e(x.get("scale",""))}</td><td>{e(x.get("file_count",""))}</td>'
        f'<td><code>{e((x.get("prompt_sha256") or "")[:12])}</code></td></tr>' for x in dataset_entries)
    detailed_ids = ['sandbox-natural-11', 'sandbox-natural-09', 'sandbox-natural-08', 'sandbox-natural-02']
    case_cards = []
    for entry in dataset_entries:
        if entry['id'] not in detailed_ids:
            continue
        truth = entry['truth']
        case_json = entry['case_json']
        case_cards.append(f'''<details class="case-card" open>
<summary><code>{e(entry['id'])}</code> <span class="muted">{e(entry.get('status',''))} · {e(entry.get('split',''))}</span></summary>
<div class="case-grid"><div><h4>Input prompt</h4><pre>{e(entry['prompt'])}</pre></div>
<div><h4>Grading</h4><p class="muted">Case config and truth are frozen; the grader runs outside the jail. Checks: structured report, real tool-call id, verbatim quote, quote supports the layer, blocker label, completion and pass.</p><details><summary>case.json</summary><pre>{e(case_json)}</pre></details><details><summary>truth.json</summary><pre>{e(truth)}</pre></details></div></div>
</details>''')
    legacy_case_cards = []
    seen = set()
    for c in legacy_cases:
        if c['case'] in seen:
            continue
        seen.add(c['case'])
        prompts = ''.join(f'<pre>{e(p)}</pre>' for p in c['prompts'])
        legacy_case_cards.append(f'''<details class="case-card"><summary><code>{e(c['case'])}</code> <span class="muted">legacy art-creation · {e(c['report_title'])}</span></summary><div class="case-grid"><div><h4>Input prompt(s)</h4>{prompts or '<p class="muted">Prompt is stored in the legacy bundle.</p>'}</div><div><h4>Case fingerprint</h4><pre>{e(c['fingerprint'])}</pre></div></div></details>''')
    all_case_cards = ''.join(
        f'<details class="case-card"><summary><code>{e(x["id"])}</code> <span class="muted">{e(x.get("status",""))} · {e(x.get("split",""))}</span></summary><div class="case-grid"><div><h4>Input prompt</h4><pre>{e(x["prompt"]) or "—"}</pre></div><div><h4>Truth / config</h4><p class="muted">Prompt SHA <code>{e((x.get("prompt_sha256") or "")[:16])}</code> · case SHA <code>{e((x.get("case_sha256") or "")[:16])}</code> · grader SHA <code>{e((x.get("grader_sha256") or "")[:16])}</code></p></div></div></details>'
        for x in dataset_entries)

    # --- skill diff blocks ---

    diff_blocks = []
    for name, text in controls.items():
        diff_blocks.append(f'<div class="diff-pair" data-pair="{e(name)}"><h3>{e("dsh-sandbox-attribution")} vs {e(name)}</h3>{diff_html(skill_text, text)}</div>')
    diff_blocks.append(f'<div class="diff-pair" data-pair="empty"><h3>{e("dsh-sandbox-attribution")} vs empty baseline</h3>{diff_html("", skill_text)}</div>')
    legacy_skill_rows = ''.join(
        f'<tr><td>{e(r["report_title"])}</td><td>{e(r["case"])}</td><td>{e(r["arm"])}</td><td><code>{e((r["skill"] or "")[:16])}</code></td></tr>'
        for r in legacy_rows[:80])

    attr_table = []
    for case in attr_cases:
        for arm in case['arms']:
            attr_table.append(f'<tr><td><code>{e(case["case"])}</code></td><td>{e(case["truth"])}</td><td>{badge(arm["arm"])}</td>'
                              f'<td>{pct(arm["semantic"], arm["valid_n"])}</td><td>{pct(arm["evidence"], arm["valid_n"])}</td><td>{e(case["title"])}</td></tr>')
    notes = summary['limitations']
    # --- trend analysis text ---
    b_ev = attr_evidence['B']
    b_n = attr_total['B']
    a_ev = attr_evidence['A0']
    a_n = attr_total['A0']
    trend_text = (f'Attribution: B evidence {pct(b_ev, b_n)} vs A0 {pct(a_ev, a_n)}; '
                  f'B semantic {pct(attr_semantic["B"], b_n)} vs A0 {pct(attr_semantic["A0"], a_n)}. '
                  f'The gap is evidence completeness, not layer recognition. '
                  f'Legacy art-creation quality is a separate scale; do not merge it with attribution scores.')
    legacy_delta = []
    for rid in report_ids:
        p = quality_by.get((rid, 'previous'), [])
        c = quality_by.get((rid, 'candidate'), [])
        if p and c:
            legacy_delta.append(f"{report_titles[rid]}: candidate {num(sum(c)/len(c),1)}% vs previous {num(sum(p)/len(p),1)}%")
    trend_text += ' Legacy report deltas: ' + ('; '.join(legacy_delta) if legacy_delta else '—') + '.'

    html_doc = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unified evaluation · DSH skills</title>
<style>
:root{{--canvas:#f6f8fa;--surface:#fff;--soft:#f0f3f6;--fg:#1f2328;--muted:#59636e;--line:#d1d9e0;--accent:#0969da;--pass:#1a7f37;--part:#9a6700;--fail:#cf222e;--radius:8px}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--canvas);color:var(--fg);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;font-variant-numeric:tabular-nums}}
header{{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;gap:.35rem 1.1rem;align-items:baseline;padding:.6rem 1.5rem;border-bottom:1px solid var(--line);background:rgba(255,255,255,.96);backdrop-filter:blur(8px)}}
header strong{{font-size:13px;letter-spacing:.05em;text-transform:uppercase}}header a{{color:var(--muted);text-decoration:none;font-size:13px;padding:.2rem 0;border-bottom:2px solid transparent}}header a:hover{{color:var(--fg)}}header a[aria-current]{{color:var(--fg);font-weight:600;border-bottom-color:var(--accent)}}
main{{max-width:1440px;margin:0 auto;padding:1.2rem 1.5rem 3rem}}h1{{font-size:22px;margin:.2rem 0 .4rem}}h2{{font-size:15px;margin:0}}h3{{font-size:13px;margin:0 0 .4rem}}h4{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:.2rem 0 .4rem}}
.muted{{color:var(--muted)}}.eyebrow{{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}.page-head{{margin:.2rem 0 1rem}}.page-head p{{margin:.2rem 0;color:var(--muted);max-width:88ch}}
.stat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:.6rem;margin:.8rem 0 1rem}}.stat{{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:.65rem .75rem}}.stat b{{display:block;font-size:21px;line-height:1.2;font-weight:650;letter-spacing:-.02em}}.stat span{{display:block;margin-top:.15rem;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em}}
.panel{{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);margin:1rem 0}}.panel-head{{display:flex;justify-content:space-between;gap:1rem;align-items:baseline;padding:.55rem .8rem;border-bottom:1px solid var(--line);background:var(--soft)}}.panel-body{{padding:.8rem}}.note{{background:#fffaeb;border:1px solid #fedf89;border-radius:var(--radius);padding:.65rem .8rem;margin:.8rem 0}}
.grid2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}}.chart{{width:100%;height:auto;display:block}}.axis{{font-size:11px;fill:var(--muted)}}.grid{{stroke:#e4e7ec;stroke-width:1}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border-bottom:1px solid #e4e7ec;padding:.4rem .5rem;text-align:left;vertical-align:top}}th{{background:#f9fafb;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}code,.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}}
.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:var(--radius)}}.table-scroll{{}}
.pill{{display:inline-block;border-radius:999px;padding:.05rem .45rem;font-size:11px;font-weight:600;border:1px solid transparent}}.pill.B,.pill.candidate{{background:#ddf4ff;color:#0969da;border-color:#b6e3ff}}.pill.A0,.pill.previous,.pill.none{{background:#eef1f4;color:#59636e;border-color:#d1d9e0}}.pill.pass{{background:#dafbe1;color:#1a7f37}}.pill.partial{{background:#fff8c5;color:#9a6700}}.pill.fail{{background:#ffebe9;color:#cf222e}}.pill.unverifiable{{background:#f0f3f6;color:#59636e}}
.case-card{{border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);margin:.6rem 0;padding:.4rem .7rem}}.case-card summary{{cursor:pointer;padding:.35rem 0}}.case-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:1rem;padding:.4rem 0 .6rem}}pre{{white-space:pre-wrap;word-break:break-word;background:#f6f8fa;border:1px solid #e4e7ec;border-radius:6px;padding:.55rem;font-size:11px;line-height:1.45;overflow:auto}}
.diff{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11px;line-height:1.4;border:1px solid var(--line);border-radius:6px;overflow:auto;background:#fff}}.diff-line{{display:grid;grid-template-columns:34px 34px minmax(0,1fr);gap:.4rem;padding:0 .4rem;white-space:pre-wrap}}.diff-line .ln{{color:#8c959f;text-align:right;user-select:none}}.diff-line.add{{background:#e6ffec}}.diff-line.del{{background:#ffebe9}}.diff-line.hunk{{background:#ddf4ff;color:#0969da}}.diff-line.meta{{color:#8c959f}}
.toolbar{{display:flex;flex-wrap:wrap;gap:.6rem;align-items:end;margin:.7rem 0}}.toolbar label{{display:grid;gap:.2rem;font-size:11px;color:var(--muted)}}select,input{{font:inherit;padding:.25rem .45rem;border:1px solid #8c959f;border-radius:6px;background:#fff}}a{{color:var(--accent);text-underline-offset:2px}}
.links a{{margin-right:1rem}}@media(max-width:700px){{header{{padding:.5rem .8rem}}main{{padding:.8rem}}.grid2{{grid-template-columns:1fr}}}}
</style></head><body class="{body_class}">
<style>.dsh-only .legacy-only{{display:none}}</style>{nav_html}
<main>
<div class="page-head" id="overview"><div class="eyebrow">Benchmark report</div><h1>DSH sandbox attribution</h1><p>Sealed attribution records; semantic accuracy and evidence completeness are reported separately.</p></div>
<div class="stat-grid">
<div class="stat"><b>{len(records)}</b><span>sealed records</span></div>
<div class="stat"><b>{len(dataset_entries)}</b><span>dataset cases</span></div>
<div class="stat"><b>{pct(b_ev, b_n)}</b><span>B evidence</span></div>
<div class="stat"><b>{pct(a_ev, a_n)}</b><span>A0 evidence</span></div>
<div class="stat"><b>{pct(attr_semantic["B"], b_n)}</b><span>B semantic</span></div>
<div class="stat"><b>{pct(attr_semantic["A0"], a_n)}</b><span>A0 semantic</span></div>
</div>
<div class="note"><strong>Read this first:</strong> semantic accuracy is an independent blind judge; evidence completeness is the frozen grader. No scalar combines suites.</div>
<section class="panel"><div class="panel-head"><h2>Attribution signal</h2><span class="muted">semantic vs evidence, by case and arm</span></div><div class="panel-body"><div class="grid2"><div>{attr_chart}<p class="muted">Semantic judges can identify the layer; evidence completeness is the measured skill increment.</p></div><div>{record_chart}<p class="muted">Sealed records: share whose grader `passed` is true.</p></div></div></div></section>
<section class="panel {legacy_class}"><div class="panel-head"><h2>Legacy art-creation quality</h2><span class="muted">normalized atom-rating mean, not comparable with attribution</span></div><div class="panel-body"><div class="grid2"><div>{legacy_quality_chart}<p class="muted">Mean quality per report and arm (0–100 over verifiable atoms).</p></div><div>{outcome_chart}<p class="muted">Atom outcomes: pass=2, partial=1, fail=0, unverifiable excluded from quality.</p></div></div><div>{legacy_trend_chart}<p class="muted">Report-order trend. Three reports are not a time series; read as a sequence of frozen snapshots.</p></div><div>{legacy_case_chart}<p class="muted">Per-case mean quality by arm across all legacy reports.</p></div></div></section>
<section class="panel"><div class="panel-head"><h2>Trend analysis</h2><span class="muted">computed from the tables below</span></div><div class="panel-body"><p>{e(trend_text)}</p><ul>{''.join(f'<li>{e(x)}</li>' for x in notes)}</ul></div></section>
<section class="panel" id="attribution"><div class="panel-head"><h2>Attribution cases</h2><span class="muted">B = with skill, A0 = without skill</span></div><div class="panel-body"><div class="table-wrap"><table><thead><tr><th>Case</th><th>Truth</th><th>Arm</th><th>Semantic</th><th>Evidence</th><th>Scenario</th></tr></thead><tbody>{''.join(attr_table)}</tbody></table></div><p class="links"><a href="records/">Machine-readable records</a><a href="METRICS_ATTRIBUTION.md">Metrics definition</a><a href="PREREGISTRATION_ATTRIBUTION.md">Preregistration</a></p></div></section>
<section class="panel {legacy_class}" id="legacy"><div class="panel-head"><h2>Art-creation legacy suites</h2><span class="muted">normalized unified table shape</span></div><div class="panel-body"><div class="toolbar"><label>Report<select id="legacy-report"><option value="">All reports</option>{''.join(f'<option value="{e(r["id"])}">{e(r["title"])}</option>' for r in legacy_reports)}</select></label><label>Arm<select id="legacy-arm"><option value="">All arms</option><option value="previous">previous</option><option value="candidate">candidate</option><option value="none">none</option></select></label></div><div class="table-wrap table-scroll"><table id="legacy-table"><thead><tr><th>Suite</th><th>Case</th><th>Split</th><th>Arm</th><th>State</th><th>Score</th><th>Scored</th><th>Model</th><th>Skill</th><th>Duration</th><th>Report</th></tr></thead><tbody>{''.join(leg_rows)}</tbody></table></div><p class="muted">Score is normalized quality (0–100). Scored shows verifiable atoms / all atoms. Legacy artifacts remain on the art-creation site.</p></div></section>
{''.join(report_sections)}
<section class="panel" id="cases"><div class="panel-head"><h2>Cases and datasets</h2><span class="muted">frozen prompts, truth and grader</span></div><div class="panel-body"><div class="toolbar"><label>Search cases<input id="case-search" placeholder="id, split, status"></label></div><div class="table-wrap table-scroll"><table id="dataset-table"><thead><tr><th>Case</th><th>Split</th><th>Status</th><th>Scale</th><th>Files</th><th>Prompt SHA</th></tr></thead><tbody>{dataset_rows}</tbody></table></div><h3 style="margin-top:1rem">Active attribution cases</h3>{''.join(case_cards)}<h3 style="margin-top:1rem">All dataset cases and prompts</h3>{all_case_cards}<div class="{legacy_class}"><h3 style="margin-top:1rem">Legacy art-creation cases</h3>{''.join(legacy_case_cards)}</div></div></section>
<section class="panel" id="skill"><div class="panel-head"><h2>Skill diff and versions</h2><span class="muted">current attribution skill vs controls and empty baseline</span></div><div class="panel-body"><div class="toolbar"><label>Diff<select id="diff-select">{''.join(f'<option value="{e(n)}">{e(n)}</option>' for n in list(controls) + ["empty"])}</select></label></div><p class="muted">Current skill: <code>skills/dsh-sandbox-attribution/SKILL.md</code> · {len(skill_text.splitlines())} lines · sha256 <code>{skill_hash[:16]}</code>. Controls live under <code>benchmarks/evaluation/controls/</code>; they are experimental, not production skills.</p>{''.join(diff_blocks)}<h3>Legacy skill hashes</h3><div class="table-wrap table-scroll"><table><thead><tr><th>Report</th><th>Case</th><th>Arm</th><th>Skill SHA</th></tr></thead><tbody>{legacy_skill_rows}</tbody></table></div><p class="muted">Legacy bundles store the evaluated skill hash, not a full skill snapshot; content diff for those versions is unavailable in this repository.</p></div></section>
<section class="panel" id="records"><div class="panel-head"><h2>Unified records</h2><span class="muted">newest sealed projections</span></div><div class="panel-body"><div class="table-wrap table-scroll"><table><thead><tr><th>Suite</th><th>Case</th><th>Split</th><th>Arm</th><th>State</th><th>Score</th><th>Evidence</th><th>Failed checks</th><th>Model</th><th>Skill</th><th>Record</th></tr></thead><tbody>{''.join(rec_rows)}</tbody></table></div><p class="muted">Record hashes and full checks are in <code>records/</code>. Infrastructure/incomplete attempts are not zero-quality evidence.</p></div></section>
<footer class="muted" style="margin:2rem 0;font-size:12px">Source evidence: <code>benchmarks/evaluation/evidence/</code> · Legacy source: <code>docs/research/skill-benchmark-architecture-2026-10-09/outputs/</code> · Build: <code>benchmarks/evaluation/build_public_site.py</code> · No model calls.</footer>
</main>
<script>
const showPair = (pair) => document.querySelectorAll('.diff-pair').forEach((el) => el.hidden = el.dataset.pair !== pair);
document.getElementById('diff-select').addEventListener('change', (event) => showPair(event.target.value));
showPair(document.getElementById('diff-select').value);
const filterLegacy = () => {{
  const report = document.getElementById('legacy-report').value;
  const arm = document.getElementById('legacy-arm').value;
  document.querySelectorAll('#legacy-table tbody tr').forEach((row) => {{
    row.hidden = (report && row.dataset.report !== report) || (arm && row.dataset.arm !== arm);
  }});
}};
['legacy-report', 'legacy-arm'].forEach((id) => document.getElementById(id).addEventListener('change', filterLegacy));
document.getElementById('case-search').addEventListener('input', (event) => {{
  const q = event.target.value.toLowerCase();
  document.querySelectorAll('#dataset-table tbody tr').forEach((row) => row.hidden = !row.textContent.toLowerCase().includes(q));
}});
</script>
</body></html>'''
    return html_doc


def load_legacy_media():
    """Public media records with their report-relative export paths and trial arms."""
    if LEGACY_DATA.is_file():
        return json.loads(LEGACY_DATA.read_text())['media']
    catalog = json.loads(CATALOG.read_text())
    out = []
    for item in catalog.get('reports', []):
        path = ART_ROOT / item['path'] / 'report.json'
        if not path.is_file():
            continue
        data = json.loads(path.read_text())
        arms = {t.get('id'): t.get('arm') for t in data.get('trials', [])}
        for m in data.get('media', []):
            if m.get('privacy') != 'public':
                continue
            export = str(m.get('export_path') or '')
            if not export.startswith('media/') or '..' in Path(export).parts:
                continue
            out.append({'report': item['id'], 'report_title': item.get('title'), 'case': m.get('case_id'),
                        'trial': m.get('trial_id'), 'arm': arms.get(m.get('trial_id')), 'turn': m.get('turn'),
                        'name': m.get('name'), 'kind': m.get('kind'), 'sha': m.get('sha256'),
                        'export': export, 'scope': m.get('scope'), 'license': m.get('license')})
    return out
