"""One entry point for evaluation records and the unified report.

Examples:
  PYTHONPATH=benchmarks/evaluation/src python3 -m eval_framework.cli ingest-agent-eval
  PYTHONPATH=benchmarks/evaluation/src python3 -m eval_framework.cli build-site
  PYTHONPATH=benchmarks/evaluation/src python3 -m eval_framework.cli validate
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .adapters import agent_eval, replays, skill_bench
from .report import build_site
from .store import FileRecordStore


def ingest(args) -> int:
    root = Path(args.agent_eval_root)
    store = FileRecordStore(Path(args.records))
    count = 0
    for record in agent_eval.records(root):
        try:
            store.seal(record)
            count += 1
        except Exception as error:
            if 'already exists' not in str(error):
                raise
    print(f'ingested {count} new records into {store.root}')
    return 0


def ingest_replays(args) -> int:
    store = FileRecordStore(Path(args.records))
    count = 0
    for record in replays.records(Path(args.replays_root)):
        try:
            store.seal(record)
            count += 1
        except Exception as error:
            if 'already exists' not in str(error):
                raise
    print(f'ingested {count} new replay records into {store.root}')
    return 0


def site(args) -> int:
    store = FileRecordStore(Path(args.records))
    records = store.list()
    published = skill_bench.published(Path(args.catalog)) if args.catalog else []
    manifest = build_site(records, published, Path(args.out), Path(args.catalog) if args.catalog else None)
    print(f'built {args.out}: {manifest["records"]} records, {len(published)} published legacy reports')
    return 0


def validate(args) -> int:
    records = FileRecordStore(Path(args.records)).list()
    print(f'validated {len(records)} records')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='eval-framework')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('ingest-agent-eval')
    p.add_argument('--agent-eval-root', default='benchmarks/agent_eval')
    p.add_argument('--records', default='benchmarks/evaluation/records')
    p.set_defaults(func=ingest)
    p = sub.add_parser('ingest-replays')
    p.add_argument('--replays-root', default='benchmarks/evaluation/replays')
    p.add_argument('--records', default='benchmarks/evaluation/records')
    p.set_defaults(func=ingest_replays)
    p = sub.add_parser('build-site')
    p.add_argument('--records', default='benchmarks/evaluation/records')
    p.add_argument('--catalog', default='benchmarks/results/catalog.json')
    p.add_argument('--out', default='benchmarks/evaluation/site')
    p.set_defaults(func=site)
    p = sub.add_parser('validate')
    p.add_argument('--records', default='benchmarks/evaluation/records')
    p.set_defaults(func=validate)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
