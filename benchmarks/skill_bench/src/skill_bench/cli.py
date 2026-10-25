"""Explicit CLI commands for freezing, execution, review and report export."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from .contracts import load_suite
from .experiment import backend, load_experiment, prepare_experiment
from .grading import calibrate
from .runner import load_regrade, regrade, run_experiment
from .store import load_results, read_events


def regular_json(root, relative):
    """Read bounded ordinary JSON before allowing any review-store adoption."""
    from .review import checked_file, MAX_JSON_BYTES
    path, data = checked_file(Path(root), relative, max_bytes=MAX_JSON_BYTES)
    if path.stat().st_nlink != 1:
        raise ValueError('Review JSON must be a regular, unlinked file')
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError('Review JSON must contain an object')
    return value


def review_mapping(run, packet):
    identifier = packet.get('review_id')
    if not isinstance(identifier, str) or not re.fullmatch(r'[0-9a-f]{24}', identifier):
        raise ValueError('Invalid anonymous review identity')
    return regular_json(Path(run).resolve(), 'reviews/' + identifier + '.arm-map.json')


def frozen_rating(run, path):
    root, target = Path(run).resolve(), Path(path).absolute()
    if '..' in target.parts or not target.is_relative_to(root / 'reviews/ratings'):
        raise ValueError('Report ratings must be frozen under this run reviews/ratings directory')
    return regular_json(root, target.relative_to(root).as_posix())


def parser():
    p = argparse.ArgumentParser(description='Versioned skill experiments with private evidence and independent review.')
    sub = p.add_subparsers(dest='command', required=True)
    validate = sub.add_parser('validate', help='Validate a frozen suite and assets; optionally calibrate trusted fixtures.')
    validate.add_argument('--suite', required=True, type=Path)
    doctor = sub.add_parser('doctor', help='Check runtime and command sandbox with zero model calls.')
    doctor.add_argument('--backend', choices=['local-codex', 'harbor'], default='local-codex')
    doctor.add_argument('--renderer', type=Path)
    doctor.add_argument('--browser', type=Path, help='Probe this Chromium installation inside the command sandbox.')
    doctor.add_argument('--blender', type=Path, help='Probe this Blender installation and native reopening inside the command sandbox.')
    plan = sub.add_parser('plan', help='Freeze inputs, skill versions and an invocation budget; never call a model.')
    plan.add_argument('--suite', required=True, type=Path)
    plan.add_argument('--case', action='append', dest='cases')
    plan.add_argument('--previous', type=Path)
    plan.add_argument('--candidate', type=Path)
    plan.add_argument('--repo', type=Path, help='Local Git repository for exact committed skill inputs.')
    plan.add_argument('--previous-ref', help='Previous local Git commit/ref; requires --candidate-ref and --repo.')
    plan.add_argument('--candidate-ref', help='Candidate local Git commit/ref, sealed before generation.')
    plan.add_argument('--skill-path', help='Repository-relative skill directory; required for commit inputs.')
    plan.add_argument('--arms', default='previous,candidate')
    plan.add_argument('--output', required=True, type=Path)
    plan.add_argument('--model', default='gpt-6.1-sol')
    plan.add_argument('--effort', default='low')
    plan.add_argument('--backend', choices=['local-codex', 'harbor'], default='local-codex')
    plan.add_argument('--renderer', type=Path)
    plan.add_argument('--browser', type=Path, help='Explicit Chromium executable; required browser cases otherwise use the bounded default.')
    plan.add_argument('--blender', type=Path, help='Explicit Blender executable; required scene cases otherwise use the bounded default.')
    plan.add_argument('--repeats', type=int, default=1)
    plan.add_argument('--max-calls', type=int, default=12)
    plan.add_argument('--wall-seconds', type=int, default=5400)
    plan.add_argument('--timeout', type=int, default=600)
    plan.add_argument('--seed', type=int, default=20261009)
    run = sub.add_parser('run', help='Inspect state; --execute starts the frozen experiment once.')
    run.add_argument('--run', required=True, type=Path)
    run.add_argument('--execute', action='store_true')
    run.add_argument('--budget-root', type=Path)
    run.add_argument('--total-max-calls', type=int, default=69)
    imp = sub.add_parser('import-legacy', help='Freeze a historical pilot without changing its original records.')
    imp.add_argument('--source', required=True, type=Path)
    imp.add_argument('--output', required=True, type=Path)
    review = sub.add_parser('review', help='Export anonymous raster evidence or validate and freeze independent ratings.')
    review.add_argument('--run', type=Path)
    review.add_argument('--output', type=Path)
    review.add_argument('--case', action='append', dest='cases', help='Export only these frozen case IDs (repeatable), allowing sealed completed cases to be reviewed while others run; selection is not score-based.')
    review.add_argument('--seed', type=int, default=20261009)
    review.add_argument('--view', choices=['artifact-only', 'notes-process', 'notes-process-v2'], default='artifact-only')
    review.add_argument('--evidence-scope', choices=['legacy', 'failed-turn-v1'], default='legacy', help='Opt into hash-bound failed-turn scope: withhold persisted files when no model output was observed; retain partial snapshots with an explicit label. Existing packets are unchanged.')
    review.add_argument('--max-package-mib', type=int, choices=range(1, 257), default=64, metavar='1..256', help='Explicit aggregate review package ceiling in MiB (default: 64); never adds generation calls.')
    review.add_argument('--allow-private', action='store_true')
    review.add_argument('--packet', type=Path)
    review.add_argument('--ratings', type=Path)
    review.add_argument('--regrade', type=Path, help='Include immutable independent source captures in the anonymous review.')
    report = sub.add_parser('report', help='Export sanitized interactive reports and preserve cohort breaks.')
    report.add_argument('--run', required=True, type=Path)
    report.add_argument('--output', required=True, type=Path)
    report.add_argument('--history', type=Path)
    report.add_argument('--review-packet', type=Path, action='append', default=[])
    report.add_argument('--ratings', type=Path, action='append', default=[])
    report.add_argument('--regrade', type=Path, help='Use one immutable verifier result without calling generation.')
    local_report = sub.add_parser('local-report', help='Export authorized private raster evidence into a new local-only directory outside Git; never run models.')
    local_report.add_argument('--run', required=True, type=Path)
    local_report.add_argument('--output', required=True, type=Path)
    local_report.add_argument('--review-packet', type=Path, action='append', default=[])
    local_report.add_argument('--ratings', type=Path, action='append', default=[])
    local_report.add_argument('--regrade', type=Path, help='Use one sealed independent verifier result without calling generation.')
    local_report.add_argument('--evidence-scope', choices=['legacy', 'failed-turn-v1'], default='legacy', help='Opt into failed-turn evidence handling; scoped frozen review packets also retain their own condition automatically.')
    grade = sub.add_parser('regrade', help='Append independent mechanical verification with zero generation calls.')
    grade.add_argument('--run', required=True, type=Path)
    grade.add_argument('--reopen-svg', action='store_true', help='Rebuild frozen SVG source and test one bounded style edit in the verified sandbox.')
    grade.add_argument('--reopen-sources', action='store_true', help='Verify SVG, actual browser playback and native Blender scenes using sealed sources.')
    from .publication import DEFAULT_REPORTS
    from .result_packages import DEFAULT_CATALOG
    pack = sub.add_parser('pack-report', help='Package validated public JSON and images as a new ZIP; print catalog metadata without running models.')
    pack.add_argument('--report', required=True, type=Path)
    pack.add_argument('--output', required=True, type=Path)
    catalog = sub.add_parser('check-catalog', help='Validate the committed result package index without downloads or model calls.')
    catalog.add_argument('--catalog', type=Path, default=Path(DEFAULT_CATALOG))
    fetch = sub.add_parser('fetch-results', help='Restore verified public result ZIPs and rebuild HTML into a new local collection; never run models.')
    fetch.add_argument('--catalog', type=Path, default=Path(DEFAULT_CATALOG))
    fetch.add_argument('--output', type=Path, default=Path(DEFAULT_REPORTS))
    fetch.add_argument('--archives', type=Path, help='Read ZIPs from this local folder instead of downloading; names must match the catalog URLs.')
    check = sub.add_parser('check-reports', help='Check submitted public report bundles with zero model calls.')
    check.add_argument('--root', type=Path, default=Path(DEFAULT_REPORTS))
    site_check = sub.add_parser('check-site', help='Check a published shared-image site, its renderer and asset hashes; never run models.')
    site_check.add_argument('--root', required=True, type=Path)
    publish = sub.add_parser('publish', help='Stage verified submitted reports into a new offline site; never run models.')
    publish.add_argument('--root', type=Path, default=Path(DEFAULT_REPORTS))
    publish.add_argument('--output', required=True, type=Path)
    portable = sub.add_parser('portable', help='Embed verified raster images in one HTML for app previews; never run models.')
    portable.add_argument('--report', required=True, type=Path)
    portable.add_argument('--output', required=True, type=Path)
    portable.add_argument('--suite-id', help='Select one benchmark suite when exporting a multi-suite site.')
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        if args.command == 'validate':
            suite = load_suite(args.suite)
            value = {'valid': True, 'suite': suite['id'], 'sha256': suite['_suite_sha256'],
                     'cases': len(suite['cases']), 'splits': {split: sum(c['split'] == split for c in suite['cases']) for split in ('development', 'holdout')}}
            if (args.suite.parent / 'calibration/manifest.json').is_file():
                value['calibration'] = calibrate(args.suite.parent)
                if not value['calibration']['pass']:
                    raise ValueError('Trusted grading calibration did not pass')
        elif args.command == 'doctor':
            from .visual_runtime import discover
            config = {'renderer': str(args.renderer)} if args.renderer else {}
            required = (['browser_capture'] if args.browser else []) + (['blender'] if args.blender else [])
            config['visual_tools'] = discover({'browser': args.browser, 'blender': args.blender}, required)
            value = backend(args.backend).doctor(config)
        elif args.command == 'plan':
            names = args.arms.split(',')
            if len(names) != len(set(names)) or not set(names).issubset({'none', 'previous', 'candidate'}):
                raise ValueError('Arms must be distinct none, previous or candidate identifiers')
            sources = {name: None if name == 'none' else getattr(args, name) for name in names}
            def prepare(sources, provenance=None):
                return prepare_experiment(args.suite, args.output, selected=args.cases, arms=sources,
                repeats=args.repeats, max_calls=args.max_calls, wall_seconds=args.wall_seconds,
                timeout=args.timeout, seed=args.seed, backend_id=args.backend, renderer=args.renderer,
                model=args.model, effort=args.effort, commit_provenance=provenance,
                browser=args.browser, blender=args.blender)
            if args.repo or args.previous_ref or args.candidate_ref:
                if not all((args.repo, args.previous_ref, args.candidate_ref)) or args.previous or args.candidate:
                    raise ValueError('Use --repo/--previous-ref/--candidate-ref together, without skill directories')
                if not args.skill_path:
                    raise ValueError('Commit inputs require an explicit --skill-path for the skill being evaluated')
                from .manual import committed_skills
                with committed_skills(args.repo, args.previous_ref, args.candidate_ref, skill_path=args.skill_path) as (committed, provenance):
                    manifest = prepare({name: None if name == 'none' else committed[name] for name in names}, provenance)
            else:
                manifest = prepare(sources)
            value = {'planned': True, 'model_called': False, 'id': manifest['id'],
                     'fingerprint': manifest['fingerprint'], 'limits': manifest['limits'], 'trials': len(manifest['schedule'])}
        elif args.command == 'run':
            value = run_experiment(args.run, execute=args.execute, budget_root=args.budget_root, max_total_calls=args.total_max_calls)
        elif args.command == 'import-legacy':
            from .legacy import import_legacy
            manifest = import_legacy(args.source, args.output)
            value = {'imported': True, 'id': manifest['id'], 'generation_calls': 0, 'trials': len(manifest['schedule'])}
        elif args.command == 'review':
            from .review import export_review, freeze_review, validate_packet_mapping
            if args.packet and args.ratings:
                if args.cases:
                    raise ValueError('Case selection applies to review export, not frozen rating import')
                if args.evidence_scope != 'legacy':
                    raise ValueError('Evidence scope applies to export; rating import uses the frozen packet condition')
                if not args.run:
                    raise ValueError('Use --run as the private destination for frozen ratings')
                packet = regular_json(args.packet, 'review.json')
                mapping = review_mapping(args.run, packet)
                validate_packet_mapping(packet, mapping)
                ratings = regular_json(args.ratings.parent, args.ratings.name)
                value = freeze_review(packet, ratings, args.run / 'reviews/ratings', media_root=args.packet)
            elif args.run and args.output:
                packet = export_review(args.run, args.output, seed=args.seed, view=args.view, allow_private=args.allow_private,
                                       regrade_path=args.regrade, max_total_bytes=args.max_package_mib * 1024 * 1024, selected_cases=args.cases, evidence_scope=args.evidence_scope)
                value = {'review_id': packet['review_id'], 'entries': len(packet['entries']), 'pairs': len(packet['pairs']), 'privacy': packet['privacy']}
            else:
                raise ValueError('Use --run/--output to export or --run/--packet/--ratings to import')
        elif args.command == 'regrade':
            value = regrade(args.run, reopen_sources=args.reopen_svg or args.reopen_sources)
            value = {'id': value['id'], 'generation_calls': 0, 'results': len(value['results']), 'quality_status': value['quality_status']}
        elif args.command in {'report', 'local-report'}:
            from .report import build_report, export_report, validate_public_bundle
            if len(args.review_packet) != len(args.ratings):
                raise ValueError('Every --review-packet requires one --ratings')
            manifest = load_experiment(args.run)
            results = load_results(args.run)
            if args.regrade:
                verifier = load_regrade(args.run, args.regrade)
                results = verifier['results']
                manifest['mechanical_verifier'] = {'sha256': verifier['verifier_sha256'],
                    'regrade_id': verifier['id'], 'source_verifier_sha256': verifier['source_verifier_sha256'],
                    'source_runtime_fingerprint': verifier['source_runtime_fingerprint'],
                    'reopen_sources': verifier['reopen_sources']}
            reviews, roots = [], {}
            for directory, rating_path in zip(args.review_packet, args.ratings):
                packet = regular_json(directory, 'review.json')
                document = frozen_rating(args.run, rating_path)
                from .review import canonical_hash
                if document.get('frozen') is not True or canonical_hash(document.get('review')) != document.get('sha256'):
                    raise ValueError('Frozen independent rating record fingerprint mismatch')
                document = document['review']
                mapping = review_mapping(args.run, packet)
                reviews.append({'packet': packet, 'document': document, 'arm_map': mapping})
                roots[packet['review_id']] = directory
            if args.command == 'local-report':
                from .private_report import build_local_report, export_local_report
                from .review import canonical_hash, validate_review
                for bundle in reviews:
                    validate_review(bundle['packet'], bundle['document'], media_root=roots[bundle['packet']['review_id']])
                report = build_local_report(manifest, results, reviews, execution_events=read_events(args.run), skill_root=args.run, evidence_scope=args.evidence_scope)
                report['review_bindings'] = [{'review_id': bundle['packet']['review_id'], 'packet_sha256': canonical_hash(bundle['packet']), 'rating_sha256': canonical_hash(bundle['document']), 'version': bundle['document']['version']} for bundle in reviews]
                value = {**export_local_report(report, args.output, media_root=args.run, packet_roots=roots), 'sample_sizes': report['sample_sizes'], 'failures': report['failures']}
            elif args.history:
                report = build_report(manifest, results, reviews, execution_events=read_events(args.run), skill_root=args.run)
                from .publication import combine_public_reports
                with tempfile.TemporaryDirectory(prefix='skill-report-current-') as temporary:
                    current = Path(temporary) / 'current'
                    export_report(report, current, media_root=args.run, packet_roots=roots)
                    previous = [p.parent for p in sorted(args.history.glob('*/report.json'))]
                    report, public_roots = combine_public_reports([*previous, current])
                    export_report(report, args.output, public_roots=public_roots)
            else:
                report = build_report(manifest, results, reviews, execution_events=read_events(args.run), skill_root=args.run)
                export_report(report, args.output, media_root=args.run, packet_roots=roots)
            if args.command == 'report':
                value = {**validate_public_bundle(args.output), 'sample_sizes': report['sample_sizes'], 'failures': report['failures']}
        elif args.command == 'pack-report':
            from .result_packages import pack_report
            value = pack_report(args.report, args.output)
        elif args.command == 'check-catalog':
            from .result_packages import load_catalog
            catalog = load_catalog(args.catalog)
            value = {'valid': True, 'suites': len(catalog['suites']), 'reports': len(catalog['reports']), 'generation_calls': 0}
        elif args.command == 'fetch-results':
            from .result_packages import fetch_results
            value = fetch_results(args.catalog, args.output, archives=args.archives)
        elif args.command == 'check-reports':
            from .publication import validate_collection
            value = validate_collection(args.root)
        elif args.command == 'publish':
            from .publication import publish_collection
            value = publish_collection(args.root, args.output)
        elif args.command == 'check-site':
            from .publication import validate_public_site
            value = validate_public_site(args.root)
        elif args.command == 'portable':
            from .publication import portable_report
            value = portable_report(args.report, args.output, suite_id=args.suite_id)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if not (args.command == 'doctor' and not value.get('passed')) else 1
    except (ValueError, OSError, KeyError, json.JSONDecodeError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({'error': str(error), 'command': args.command}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
