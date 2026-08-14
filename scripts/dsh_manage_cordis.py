#!/usr/bin/env python3
"""幂等地在 cordis.patch.yml 里增删 maintainall 的 cordis:include 条目。"""
import sys

MARKER = 'id: maintainall'
ENTRY = (
    '- insert:' + chr(10) +
    '    - id: maintainall' + chr(10) +
    '      name: cordis:include' + chr(10) +
    '      config:' + chr(10) +
    '        path: ./maintainall.yml'
)


def top_level_blocks(lines):
    header = []
    blocks = []
    cur = None
    for line in lines:
        if line.startswith('- '):
            if cur is not None:
                blocks.append(cur)
            cur = [line]
        elif cur is not None:
            cur.append(line)
        else:
            header.append(line)
    if cur is not None:
        blocks.append(cur)
    return header, blocks


def block_has_marker(block):
    return any(MARKER in line for line in block)


def is_insert_block(block):
    return bool(block) and block[0].strip() == '- insert:'


def join_lines(header, blocks):
    nl = chr(10)
    return nl.join(header + [line for block in blocks for line in block])


def normalize(text):
    nl = chr(10)
    lines = text.split(nl)
    while lines and lines[-1].strip() == '':
        lines.pop()
    stripped = [l for l in lines if l.strip() and not l.strip().startswith('#')]
    if not stripped:
        return nl.join(lines).rstrip(nl) + nl + '[]' + nl
    return nl.join(lines) + nl


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    action, path = sys.argv[1], sys.argv[2]
    with open(path, encoding='utf-8') as f:
        text = f.read()
    header, blocks = top_level_blocks(text.split(chr(10)))

    if action == 'add':
        if any(block_has_marker(b) for b in blocks):
            print('add: no change (' + path + ')')
            return
        blocks = [b for b in blocks if not is_insert_block(b)]
        header = [l for l in header if l.strip() not in ('[]', '')]
        new_text = normalize(join_lines(header, blocks + [ENTRY.split(chr(10))]))
    elif action == 'remove':
        if not any(block_has_marker(b) for b in blocks):
            print('remove: no change (' + path + ')')
            return
        blocks = [b for b in blocks if not (is_insert_block(b) and block_has_marker(b))]
        new_text = normalize(join_lines(header, blocks))
    else:
        sys.exit(2)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_text)
    print(action + ': updated ' + path)


if __name__ == '__main__':
    main()
