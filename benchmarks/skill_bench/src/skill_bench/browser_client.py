#!/usr/bin/env python3
"""Request bounded offline browser captures from the trusted local trial broker."""
import argparse
import json
from pathlib import Path
import time
import uuid


def relative(root, path):
    target = Path(path).absolute()
    if '..' in target.parts or not target.is_relative_to(root) or any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError('Capture paths must stay inside the real trial workspace')
    return target.relative_to(root).as_posix()


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog='Uses a file request protocol; never starts a host browser or opens a network socket. Source, spec and output remain inside this workspace. The trusted broker uses a separate offline kernel namespace because Chromium cannot run under the restricted Codex socket syscall filter. Use tools/browser_driver.py --help for the bounded spec schema. Capture proves sampled playback only, not motion quality.')
    parser.add_argument('--source', required=True, type=Path, help='Local HTML file, retaining its relative resource base.')
    parser.add_argument('--output', required=True, type=Path, help='New capture directory; no overwrite.')
    parser.add_argument('--spec', type=Path, help='Optional bounded JSON timing, profiles and real input scenario.')
    parser.add_argument('--timeout', type=float, default=90, help='Wait ceiling in seconds, 1..120 (default90).')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120:
        parser.error('timeout must be 1..120 seconds')
    root = Path(__file__).resolve().parent.parent
    queue = root / '.visual-requests'
    try:
        if not queue.is_dir() or queue.is_symlink():
            raise ValueError('No trusted browser broker is active in this workspace')
        request = {'source': relative(root, args.source), 'output': relative(root, args.output)}
        if args.spec:
            spec = Path(args.spec)
            relative(root, spec)
            if spec.stat().st_size > 65536:
                raise ValueError('Capture spec exceeds 64 KiB')
            request['spec'] = json.loads(spec.read_text())
        identifier = uuid.uuid4().hex
        path = queue / ('request-' + identifier + '.json')
        temporary = queue / ('pending-' + identifier + '.json')
        with temporary.open('x') as stream:
            json.dump(request, stream)
        temporary.rename(path)
        response = queue / ('response-' + identifier + '.json')
        deadline = time.monotonic() + args.timeout
        while not response.exists():
            if time.monotonic() >= deadline:
                raise ValueError('Browser broker response timed out; no automatic retry')
            time.sleep(.1)
        if response.is_symlink() or response.stat().st_size > 65536:
            raise ValueError('Invalid broker response')
        result = json.loads(response.read_text())
        print(json.dumps(result))
        return 0 if result.get('passed') else 1
    except (OSError, ValueError) as error:
        print(json.dumps({'passed': False, 'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
