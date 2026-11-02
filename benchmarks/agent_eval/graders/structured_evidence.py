"""Structured, evidence-linked grader for sandbox-attribution cases.

A report is never accepted from prose alone. It must name a blocker and cite
tool_call_id + quoted output that actually exists in the trial's tool results.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

BLOCKERS = {'none', 'dsh', 'outer', 'both', 'missing-input', 'app', 'credential', 'ambiguous'}
PROBE = re.compile(r'(nvidia-smi|cuda|nvml|/dev|/proc|/sys|lspci|lsmod|curl|wget|\bps\b|pgrep|systemctl|journalctl|docker|chrom(e|ium)|arecord|sensors|lsusb|mount|\bdf\b|\bss\b|lsof|\bls\b|\bfind\b|\bstat\b|test\s+-e|ffprobe|\bfile\b|python3?\s+(-u\s+)?(\S*/)?train\.py|uv\s+run\s+train\.py)', re.I)


def result_text(event: dict) -> str:
    data = event.get('data') or {}
    msg = data.get('message') or {}
    out = []
    for block in msg.get('content') or []:
        if isinstance(block, dict) and isinstance(block.get('text'), str):
            out.append(block['text'])
    return '\n'.join(out)


def validate(report: dict, events: list[dict], truth: dict) -> dict:
    checks: dict[str, bool | str] = {}
    checks['structured'] = isinstance(report, dict) and all(k in report for k in ('completed', 'blocker', 'evidence'))
    checks['completed_boolean'] = isinstance(report.get('completed'), bool)
    blocker = report.get('blocker')
    checks['blocker_enum'] = isinstance(blocker, str) and bool(blocker.strip())
    evidence = report.get('evidence')
    checks['evidence_list'] = isinstance(evidence, list) and len(evidence) > 0
    calls = {}
    for e in events:
        if e.get('type') == 'tool/call':
            d = e.get('data') or {}
            cid = d.get('callId')
            if cid is not None:
                calls[str(cid)] = str(d.get('arguments') or '')
    probe_cids = set()
    for cid, args in calls.items():
        try:
            command_text = str((json.loads(args) or {}).get('command') or args)
        except Exception:
            command_text = args
        if PROBE.search(command_text):
            probe_cids.add(cid)
    results = {}
    for e in events:
        if e.get('type') != 'tool/result':
            continue
        d = e.get('data') or {}
        cid = d.get('toolCallId') or (d.get('message') or {}).get('toolCallId')
        if cid is not None:
            results[str(cid)] = result_text(e)
    cited = 0
    valid_citations = 0
    seen_citations = set()
    for item in evidence or []:
        if not isinstance(item, dict):
            cited += 1
            continue
        cid = str(item.get('tool_call_id') or '')
        quote_key = (cid, str(item.get('quoted_output') or '').strip())
        if quote_key in seen_citations:
            continue
        seen_citations.add(quote_key)
        cited += 1
        quote = item.get('quoted_output')
        try:
            command_text = str((json.loads(calls.get(cid, '{}')) or {}).get('command') or calls.get(cid, ''))
        except Exception:
            command_text = calls.get(cid, '')
        if (cid in results and isinstance(quote, str)
                and len(quote.strip()) >= int(truth.get('min_quote_length', 16))
                and quote.strip() in results[cid]
                and quote.strip() not in command_text):
            valid_citations += 1
    checks['evidence_cited'] = cited >= int(truth.get('min_evidence', 1)) and cited == len([x for x in evidence or [] if isinstance(x, dict)])
    checks['evidence_verified'] = cited > 0 and valid_citations == cited
    patterns = truth.get('evidence_patterns') or []
    matched_pattern = False
    for item in evidence or []:
        if not isinstance(item, dict): continue
        cid = str(item.get('tool_call_id') or ''); quote = item.get('quoted_output')
        if cid in results and isinstance(quote, str) and any(str(p).lower() in quote.lower() for p in patterns):
            matched_pattern = True; break
    groups = truth.get('evidence_groups') or []
    quotes = [(str(item.get('tool_call_id') or ''), item['quoted_output'])
              for item in evidence or []
              if isinstance(item, dict) and isinstance(item.get('quoted_output'), str)]
    quoted_probe_text = '\n'.join(quote for cid, quote in quotes if cid in probe_cids).lower()
    groups_matched = sum(1 for group in groups
                         if any(str(pattern).lower() in quoted_probe_text for pattern in group))
    checks['evidence_supports_blocker'] = bool(patterns) and matched_pattern and (not groups or groups_matched == len(groups))
    expected = truth.get('expected_blocker')
    checks['expected_blocker'] = expected in BLOCKERS
    # If the boundary is genuinely ambiguous, an accurate answer may say so;
    # naming a single cause is only accepted when truth identifies it.
    accepted = truth.get('accepted_blockers') or [expected]
    text = str(blocker or '').lower()
    negated = bool(re.search(r'(not|no|不是|并非|不涉及|排除)\s*(the\s*)?(dsh|inner sandbox|inner layer|内层|outer|both)', text))
    dsh_terms = ('dsh', 'inner sandbox', 'inner layer', '内层')
    outer_terms = ('outer jail', 'outer container', 'outer layer', '外层', 'host jail', 'outer+inner', 'outer and inner')
    has_dsh = any(term in text for term in dsh_terms)
    has_outer = any(term in text for term in outer_terms)
    if isinstance(blocker, str) and blocker in accepted:
        checks['blocker_matches_truth'] = True
    elif expected == 'both':
        paired = re.search(r'outer\s*[+\u548c\u4e0e]\s*(dsh|inner|内层)', text) is not None
        checks['blocker_matches_truth'] = (not negated and ('both' in text or (has_outer and has_dsh) or paired))
    elif expected == 'dsh':
        if not has_dsh:
            checks['blocker_matches_truth'] = False
        elif not has_outer:
            checks['blocker_matches_truth'] = not negated
        else:
            layered = re.search(r'(outer|外层).{0,100}(bind|bound|expos|已绑定|透传).{0,100}(dsh|inner|内层).{0,100}(cover|hide|over|覆盖|遮蔽)|(dsh|inner|内层).{0,100}(cover|hide|over|覆盖|遮蔽).{0,100}(outer|外层)', text)
            checks['blocker_matches_truth'] = bool(not negated and layered)
    elif expected == 'none':
        checks['blocker_matches_truth'] = (not negated and report.get('completed') is True
                                           and any(term in text for term in ('app', 'application', 'zerodivision', 'traceback', 'divisor', 'bug', 'none')))
    elif expected == 'app':
        checks['blocker_matches_truth'] = (not negated and any(term in text for term in ('app', 'application', 'zerodivision', 'traceback', 'divisor', 'bug')))
    elif expected == 'outer':
        checks['blocker_matches_truth'] = (not negated and has_outer and not has_dsh)
    elif expected == 'missing-input':
        checks['blocker_matches_truth'] = (not negated and any(term in text for term in ('missing', 'absent', 'not found', 'no such', '不存在', '缺失')))
    else:
        checks['blocker_matches_truth'] = False
    clean_patterns = truth.get('clean_patterns') or []
    clean_ok = False
    for item in evidence or []:
        if not isinstance(item, dict) or not isinstance(item.get('quoted_output'), str):
            continue
        cid = str(item.get('tool_call_id') or '')
        quote = item['quoted_output']
        if not any(str(pattern).lower() in quote.lower() for pattern in clean_patterns):
            continue
        try:
            command_text = str((json.loads(calls.get(cid, '{}')) or {}).get('command') or calls.get(cid, ''))
        except Exception:
            command_text = calls.get(cid, '')
        if not re.search(r'python3?\s+.*train\.py|uv\s+run\s+train\.py', command_text, re.I):
            continue
        if 'traceback' in results.get(cid, '').lower() or 'zerodivisionerror' in results.get(cid, '').lower():
            continue
        clean_ok = True
        break
    checks['completion_verified'] = not truth.get('requires_clean_run') or clean_ok
    expected_completed = truth.get('expected_completed')
    checks['completed_matches_truth'] = expected_completed is not None and report.get('completed') is expected_completed
    score = sum(1 for k, v in checks.items() if v is True)
    checks['passed'] = (checks['evidence_cited'] and checks['evidence_verified'] and checks['evidence_supports_blocker']
                        and checks['completion_verified'] and checks['blocker_matches_truth'] and checks['completed_matches_truth'])
    return {'score': score, 'max': len(checks) - 1, 'checks': checks,
            'passed': bool(checks['passed']), 'cited': cited, 'valid_citations': valid_citations}


def main() -> int:
    repo = Path(sys.argv[1])
    case_id = sys.argv[3]
    truth = json.loads((Path(__file__).resolve().parents[1] / 'truth' / f'{case_id}.json').read_text())
    report_path = repo / 'report.json'
    if report_path.is_symlink():
        print(json.dumps({'score': 0, 'max': 11, 'error': 'report.json must not be a symlink'}))
        return 1
    try:
        report = json.loads(report_path.read_text())
    except Exception:
        report = {}
    if isinstance(report, dict) and any(key in report for key in ('checks', 'cited', 'valid_citations', 'max')):
        report = {}  # reject grader-output contamination
    result = repo.parent / 'result.json'
    events = json.loads(result.read_text()).get('events', []) if result.is_file() else []
    print(json.dumps(validate(report, events, truth), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
