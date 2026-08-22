#!/usr/bin/env python3
"""One-shot bootstrap + private-rules migration for daed.

Usage:
    python3 daed-init.py                        # initialize an empty wing.db (once)
    python3 daed-init.py export-private         # print the private rules block from wing.db
    python3 daed-init.py export-private --tag work --output private.txt
    python3 daed-init.py import-private --file private.txt [--force-groups]

`init` only writes when the corresponding table is empty, so it can never
overwrite changes made in the daed Web UI. The Web UI is the source of truth
after initialization.

Private rules are stored inside the selected routing text between markers:

    # ── private-rules:start ──
    # private-group: <name> | <policy> | <param>
    # private-tag: <tag>
    <dae routing rules>
    # ── private-rules:end ──

Use `export-private` on the old machine and `import-private` on the new one to
carry private rules across machines without committing them to git.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

try:
    import select
    import termios
    import tty
except ImportError:  # pragma: no cover - daed hosts are Linux
    select = termios = tty = None

DAED_DIR = Path(__file__).resolve().parent
CONFIG_DIR = DAED_DIR / "config"
DB_PATH = CONFIG_DIR / "wing.db"
GROUPS_FILE = CONFIG_DIR / "groups.txt"

MARKER_START = "# ── private-rules:start ──"
MARKER_END = "# ── private-rules:end ──"
GROUP_PREFIX = "# private-group:"
TAG_PREFIX = "# private-tag:"
LEGACY_MARKER = "# ── Private rules (private.conf, not version-controlled) ──"

VALID_POLICIES = {"random", "fixed", "min", "min_avg10", "min_moving_avg"}
BUILTIN_GROUPS = {"direct", "proxy", "block", "must_direct", "must_block", "must_proxy"}

# ── terminal colors ─────────────────────────────────────────────────────────

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COLOR = _color_enabled()


def paint(text: str, color: str) -> str:
    if not _COLOR:
        return text
    return f"{color}{text}{C.RESET}"


def info(msg: str) -> None:
    print(paint(f"[daed-init] {msg}", C.CYAN))


def ok(msg: str) -> None:
    print(paint(f"  ✓ {msg}", C.GREEN))


def warn(msg: str) -> None:
    print(paint(f"  ⚠ {msg}", C.YELLOW), file=sys.stderr)


def fail(msg: str) -> int:
    print(paint(f"[daed-init] error: {msg}", C.RED), file=sys.stderr)
    return 1


def migration_notice() -> None:
    box = [
        "  ─────────────────────────────────────────────────────────────",
        "  迁移提醒：private 规则/分组不会随 git 走。",
        "  旧机导出:",
        "    python3 daed-init.py export-private --output private.txt",
        "  新机导入:",
        "    python3 daed-init.py import-private --file private.txt",
        "  ─────────────────────────────────────────────────────────────",
    ]
    print()
    for line in box:
        print(paint(line, C.MAGENTA + C.BOLD))
    print()


# ── generic db helpers ──────────────────────────────────────────────────────

def wait_for_db(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if DB_PATH.is_file():
            return True
        time.sleep(0.5)
    return False


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    return cur.fetchone()[0] > 0


def table_count(conn: sqlite3.Connection, name: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]


def wrap_section(section: str, content: str) -> str:
    content = content.strip()
    return f"{section} {{\n{content}\n}}\n"


def host_interface_names() -> list[str]:
    net = Path("/sys/class/net")
    if not net.is_dir():
        return []
    return sorted(p.name for p in net.iterdir() if p.is_dir())


def interface_operstate(name: str) -> str:
    state = Path("/sys/class/net") / name / "operstate"
    try:
        return state.read_text(encoding="utf-8").strip()
    except OSError:
        return "down"


def default_route_interface() -> str | None:
    try:
        lines = Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
        return None
    for line in lines:
        parts = line.split()
        if len(parts) >= 11 and parts[1] == "00000000":
            return parts[0]
    return None


_PHYSICAL_RE = re.compile(r"^(enp|eth|wlp|wlan)")


def interface_candidates() -> list[tuple[str, str, bool]]:
    """Candidate LAN interfaces: physical NICs first, then docker0, then br-*."""
    default_route = default_route_interface()
    physical: list[tuple[str, str, bool]] = []
    bridges: list[tuple[str, str, bool]] = []
    for name in host_interface_names():
        if name == "lo" or name == "dae0" or name.startswith("veth") or name.startswith("tailscale"):
            continue
        if _PHYSICAL_RE.match(name):
            physical.append((name, interface_operstate(name), name == default_route))
        elif name == "docker0" or name.startswith("br-"):
            bridges.append((name, interface_operstate(name), name == default_route))
    return physical + bridges


def detect_lan_interfaces() -> list[str]:
    """Default selection: physical UP NICs + docker0 + UP docker bridges."""
    physical: list[str] = []
    bridges: list[str] = []
    for name, state, _ in interface_candidates():
        if name == "docker0" or name.startswith("br-"):
            if state == "up":
                bridges.append(name)
        elif state == "up":
            physical.append(name)

    if not physical:
        fallback = default_route_interface()
        if fallback:
            physical.append(fallback)

    return physical + bridges


def _read_byte(fd: int) -> str:
    try:
        data = os.read(fd, 1)
    except OSError:
        return ""
    return data.decode("utf-8", "replace") if data else ""


def _read_key(fd: int) -> str:
    """Read one key from a raw terminal fd; arrows arrive as escape sequences."""
    key = _read_byte(fd)
    if key != "\x1b":
        return key
    if select is None:
        return key
    while select.select([fd], [], [], 0.03)[0]:
        key += _read_byte(fd)
        if key in ("\x1b[A", "\x1b[B"):
            break
        if len(key) >= 6:
            break
    return key


class _RawTerminal:
    """Put stdin in raw mode for the duration of the selection UI."""

    def __enter__(self) -> "_RawTerminal":
        if termios is None or tty is None:
            return self
        self.fd = sys.stdin.fileno()
        self.old_attrs = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if termios is None or tty is None or getattr(self, "old_attrs", None) is None:
            return
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_attrs)


def _parse_index_selection(text: str, count: int) -> set[int]:
    """Parse `1 2 3`, `1,2,3`, `1-3`, and mixed forms like `1-3 5`."""
    selected: set[int] = set()
    for part in re.split(r"[\s,]+", text.strip()):
        if not part:
            continue
        range_match = re.fullmatch(r"(\d+)-(\d+)", part)
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if start > end:
                start, end = end, start
            if start < 1 or end > count:
                raise ValueError(f"范围 {part} 超出 1-{count}")
            selected.update(range(start - 1, end))
            continue
        if part.isdigit():
            index = int(part)
            if index < 1 or index > count:
                raise ValueError(f"编号 {part} 超出 1-{count}")
            selected.add(index - 1)
            continue
        raise ValueError(f"无法识别的编号: {part}")
    if not selected:
        raise ValueError("未选择任何编号")
    return selected


def interactive_multiselect(
    title: str,
    options: list[tuple[str, str]],
    defaults: list[str] | set[str] | None = None,
) -> list[str]:
    """Generic terminal multi-select.

    Keys:
        ↑/↓       move cursor
        Space     toggle the cursor item
        Ctrl+A    select all
        Ctrl+W    switch between arrow-select mode and number-input mode
                  (number mode accepts `1 2 3`, `1-3`, or mixed `1-3 5`;
                  Enter confirms)
        Enter     confirm

    Falls back to `defaults` (filtered to known option values) when stdin is
    not a TTY or the raw-terminal stack is unavailable.
    """
    if not options:
        return []

    values = [value for value, _ in options]
    default_set = set(defaults or [])
    if not (hasattr(sys.stdin, "isatty") and sys.stdin.isatty()):
        info(f"non-interactive run; using default selection: "
             f"{','.join(v for v in values if v in default_set)}")
        return [v for v in values if v in default_set]

    if termios is None or tty is None:
        return [v for v in values if v in default_set]

    selected = {value for value in values if value in default_set}
    current = 0
    mode = "arrow"  # or "input"
    input_buffer = ""
    error = ""
    rendered_lines = 0
    fd = sys.stdin.fileno()

    def selected_numbers() -> str:
        return " ".join(str(index + 1)
                        for index, value in enumerate(values)
                        if value in selected)

    def screen_lines() -> list[str]:
        lines = [paint(title, C.CYAN),
                 paint("  ↑/↓ 移动   Space 选中/取消   Ctrl+A 全选   Ctrl+W 编号输入   Enter 确认", C.CYAN)]
        for index, (value, description) in enumerate(options):
            cursor = ">" if mode == "arrow" and index == current else " "
            mark = "[x]" if value in selected else "[ ]"
            line = f"  {cursor} {mark} {value:<20} {description}"
            if value in selected:
                line = paint(line, C.GREEN)
            elif mode == "arrow" and index == current:
                line = paint(line, C.CYAN)
            lines.append(line)
        if mode == "input":
            lines.append(paint(f"  当前已选: {selected_numbers() or '无'}", C.CYAN))
            lines.append(paint(f"  编号输入: {input_buffer}_（支持混合，如: 1-3 5 或 1 3 5-7；留空回车保持当前选择）", C.CYAN))
            lines.append(paint("  Ctrl+W 返回上下选择", C.CYAN))
        if error:
            lines.append(paint(f"  {error}", C.RED))
        return lines

    def draw(lines: list[str]) -> None:
        nonlocal rendered_lines
        if rendered_lines:
            sys.stdout.write(f"\x1b[{rendered_lines}A")
            sys.stdout.write("\x1b[J")
        for line in lines:
            sys.stdout.write(line + "\r\n")
        rendered_lines = len(lines)
        sys.stdout.flush()

    try:
        sys.stdout.write("\x1b[?25l")
        sys.stdout.flush()
        with _RawTerminal():
            draw(screen_lines())
            while True:
                key = _read_key(fd)
                if key == "\x03":
                    raise KeyboardInterrupt
                if key == "\x1b[A":  # up
                    if mode == "arrow":
                        current = (current - 1) % len(options)
                elif key == "\x1b[B":  # down
                    if mode == "arrow":
                        current = (current + 1) % len(options)
                elif key == " ":
                    if mode == "arrow":
                        value = values[current]
                        if value in selected:
                            selected.discard(value)
                        else:
                            selected.add(value)
                    else:
                        input_buffer += " "
                        error = ""
                elif key == "\x01":  # Ctrl+A
                    selected = set(values)
                    input_buffer = ""
                    error = ""
                elif key == "\x17":  # Ctrl+W
                    if mode == "arrow":
                        mode = "input"
                        input_buffer = ""
                        error = ""
                    else:
                        mode = "arrow"
                        error = ""
                elif key in ("\r", "\n"):  # Enter
                    if mode == "input":
                        if input_buffer.strip():
                            try:
                                indices = _parse_index_selection(input_buffer, len(options))
                            except ValueError as exc:
                                error = str(exc)
                                draw(screen_lines())
                                continue
                            selected = {values[index] for index in indices}
                        # Empty input keeps the current arrow-mode selection.
                    break
                elif key in ("\x7f", "\x08"):  # Backspace
                    if mode == "input":
                        input_buffer = input_buffer[:-1]
                        error = ""
                elif mode == "input" and key.isprintable():
                    input_buffer += key
                    error = ""
                draw(screen_lines())
    finally:
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()

    return [value for value in values if value in selected]


def choose_lan_interfaces() -> list[str]:
    """LAN-interface multi-select backed by the generic `interactive_multiselect`."""
    candidates = interface_candidates()
    defaults = detect_lan_interfaces()
    if not candidates:
        return defaults

    options = []
    for name, state, is_default_route in candidates:
        description = state
        if is_default_route:
            description += " [default route]"
        options.append((name, description))

    return interactive_multiselect(
        "选择要绑定的 LAN 网卡（默认已勾选自动检测结果）",
        options,
        defaults,
    )


def ensure_global_conf() -> None:
    """Create config/global.conf from the tracked example when missing."""
    global_conf = CONFIG_DIR / "global.conf"
    if global_conf.is_file():
        return

    example = CONFIG_DIR / "global.conf.example"
    if not example.is_file():
        warn("config/global.conf.example not found; cannot generate config/global.conf")
        return

    content = example.read_text(encoding="utf-8")
    if "<YOUR_LAN_INTERFACE>" in content:
        ifaces = choose_lan_interfaces()
        if ifaces:
            content = content.replace("<YOUR_LAN_INTERFACE>", ",".join(ifaces))
            global_conf.write_text(content, encoding="utf-8")
            ok(f"generated config/global.conf from global.conf.example "
               f"(lan_interface: {','.join(ifaces)})")
        else:
            warn("could not detect any LAN interface; generated global.conf "
                 "still contains <YOUR_LAN_INTERFACE> — edit it before init")
            global_conf.write_text(content, encoding="utf-8")
    else:
        global_conf.write_text(content, encoding="utf-8")
        ok("generated config/global.conf from global.conf.example")


# ── init: config seeding ────────────────────────────────────────────────────

def seed_config(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    section: str,
    file: Path,
) -> bool:
    if not table_exists(conn, table):
        warn(f"skip {table}: table missing (daed not booted yet?)")
        return False

    if table_count(conn, table) > 0:
        info(f"skip {table}: already initialized")
        return False

    if not file.is_file():
        warn(f"skip {table}: {file.name} not found")
        return False

    content = wrap_section(section, file.read_text(encoding="utf-8"))
    conn.execute(
        f"INSERT INTO {table} (name, \"{column}\", selected, version) "
        "VALUES ('default', ?, 1, 0)",
        (content,),
    )
    ok(f"seeded {table} from {file.name}")
    return True


def parse_groups(file: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    if not file.is_file():
        return rows
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        while len(parts) < 3:
            parts.append("")
        name, policy, param = parts[0], parts[1], parts[2]
        if not name or policy not in VALID_POLICIES:
            warn(f"skip invalid group line: {raw}")
            continue
        rows.append((name, policy, param))
    return rows


def seed_groups(conn: sqlite3.Connection, file: Path) -> bool:
    if not table_exists(conn, "groups"):
        warn("skip groups: groups table missing (daed not booted yet?)")
        return False

    if table_count(conn, "groups") > 0:
        info("skip groups: already initialized")
        return False

    rows = parse_groups(file)
    if not rows:
        warn("skip groups: no groups in groups.txt")
        return False

    for name, policy, param in rows:
        conn.execute(
            "INSERT INTO groups (name, policy, version) VALUES (?, ?, 0)",
            (name, policy),
        )
        gid = conn.execute(
            "SELECT id FROM groups WHERE name = ?", (name,)
        ).fetchone()[0]
        ok(f"created group {name} (policy={policy})")

        if policy == "fixed":
            idx = param if param.isdigit() else "0"
            conn.execute(
                "INSERT INTO group_policy_params (key, value, group_id) "
                "VALUES ('', ?, ?)",
                (idx, gid),
            )
            conn.execute("UPDATE groups SET version = version + 1 WHERE id = ?", (gid,))

        if name != "proxy":
            ncount = conn.execute(
                "SELECT COUNT(*) FROM group_nodes WHERE group_id = ?", (gid,)
            ).fetchone()[0]
            scount = conn.execute(
                "SELECT COUNT(*) FROM group_subscriptions WHERE group_id = ?", (gid,)
            ).fetchone()[0]
            if ncount == 0 and scount == 0:
                proxy = conn.execute(
                    "SELECT id FROM groups WHERE name = 'proxy' LIMIT 1"
                ).fetchone()
                if proxy:
                    pick = conn.execute(
                        "SELECT n.id, n.name FROM nodes n "
                        "WHERE n.subscription_id IN ("
                        "  SELECT subscription_id FROM group_subscriptions "
                        "  WHERE group_id = ?"
                        ") OR n.id IN ("
                        "  SELECT node_id FROM group_nodes WHERE group_id = ?"
                        ") ORDER BY CASE n.protocol "
                        "  WHEN 'anytls' THEN 0 WHEN 'tuic' THEN 1 ELSE 2 END, "
                        "n.id LIMIT 1",
                        (proxy[0], proxy[0]),
                    ).fetchone()
                    if not pick:
                        pick = conn.execute(
                            "SELECT id, name FROM nodes ORDER BY id LIMIT 1"
                        ).fetchone()
                    if pick:
                        conn.execute(
                            "INSERT OR IGNORE INTO group_nodes (group_id, node_id) "
                            "VALUES (?, ?)",
                            (gid, pick[0]),
                        )
                        conn.execute(
                            "UPDATE groups SET version = version + 1 WHERE id = ?",
                            (gid,),
                        )
                        ok(f"seeded {name} with 1 node: {pick[1]} (id={pick[0]})")
                    else:
                        warn(f"group {name} empty and no nodes available")
                else:
                    warn(f"group {name} empty and proxy group not found")
    return True


# ── private block helpers ───────────────────────────────────────────────────

def selected_routing(conn: sqlite3.Connection) -> tuple[int, str] | None:
    row = conn.execute(
        "SELECT id, routing FROM routings WHERE selected = 1 LIMIT 1"
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT id, routing FROM routings ORDER BY id LIMIT 1"
        ).fetchone()
    return row


def public_group_names() -> set[str]:
    return {name for name, _, _ in parse_groups(GROUPS_FILE)}


def rule_refs(lines: list[str]) -> set[str]:
    refs: set[str] = set()
    for line in lines:
        if line.strip().startswith("#"):
            continue
        refs.update(re.findall(r"->\s*([A-Za-z_][A-Za-z0-9_-]*)", line))
    return refs


def group_def_from_db(conn: sqlite3.Connection, name: str) -> tuple[str, str, str] | None:
    row = conn.execute(
        "SELECT id, policy FROM groups WHERE name = ? LIMIT 1", (name,)
    ).fetchone()
    if row is None:
        return None
    gid, policy = row
    param = ""
    if policy == "fixed":
        p = conn.execute(
            "SELECT value FROM group_policy_params WHERE group_id = ? AND key = '' LIMIT 1",
            (gid,),
        ).fetchone()
        param = p[0] if p else "0"
    return name, policy, param


def parse_group_def(line: str) -> tuple[str, str, str] | None:
    body = line.strip()
    if not body.startswith(GROUP_PREFIX):
        return None
    parts = [p.strip() for p in body[len(GROUP_PREFIX):].split("|")]
    while len(parts) < 3:
        parts.append("")
    name, policy, param = parts[0], parts[1], parts[2]
    if not name:
        return None
    return name, policy, param


def parse_tag_def(line: str) -> str | None:
    body = line.strip()
    if not body.startswith(TAG_PREFIX):
        return None
    tag = body[len(TAG_PREFIX):].strip()
    return tag or None


def extract_new_block(text: str) -> str | None:
    start = text.find(MARKER_START)
    end = text.find(MARKER_END)
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start:end + len(MARKER_END)]


def extract_legacy_rules(text: str) -> list[str]:
    """Read rule lines from the old `# private-rules` injection format."""
    lines = text.splitlines()
    rules: list[str] = []
    in_block = False
    for line in lines:
        if line.strip() == LEGACY_MARKER:
            in_block = True
            continue
        if not in_block:
            continue
        stripped = line.strip()
        if stripped == "":
            break
        if stripped.startswith("#"):
            break
        rules.append(line)
    return rules


def block_from_parts(
    groups: list[tuple[str, str, str]],
    tagged_rules: list[tuple[str | None, str]],
) -> str:
    out = [MARKER_START]
    for name, policy, param in groups:
        out.append(f"{GROUP_PREFIX} {name} | {policy} | {param}")
    last_tag: str | None = object()  # sentinel: always emit first tag line
    for tag, line in tagged_rules:
        if tag is not None and tag != last_tag:
            out.append(f"{TAG_PREFIX} {tag}")
            last_tag = tag
        out.append(line)
    out.append(MARKER_END)
    return "\n".join(out) + "\n"


def block_to_parts(block: str) -> tuple[list[tuple[str, str, str]], list[tuple[str | None, str]]]:
    groups: list[tuple[str, str, str]] = []
    tagged_rules: list[tuple[str | None, str]] = []
    current_tag: str | None = None
    for line in block.splitlines():
        stripped = line.strip()
        if stripped in (MARKER_START, MARKER_END):
            continue
        group_def = parse_group_def(stripped)
        if group_def is not None:
            groups.append(group_def)
            continue
        tag = parse_tag_def(stripped)
        if tag is not None:
            current_tag = tag
            continue
        if stripped:
            tagged_rules.append((current_tag, line))
    return groups, tagged_rules


def export_private(conn: sqlite3.Connection, tag: str | None) -> str:
    row = selected_routing(conn)
    if row is None:
        raise RuntimeError("routings table is empty; run `daed-init.py` first")

    routing = row[1]
    block = extract_new_block(routing)
    if block is not None:
        groups, tagged_rules = block_to_parts(block)
    else:
        legacy = extract_legacy_rules(routing)
        if not legacy:
            raise RuntimeError("no private-rules block found in wing.db routing")
        groups = []
        for ref in sorted(rule_refs(legacy) - public_group_names() - BUILTIN_GROUPS):
            definition = group_def_from_db(conn, ref)
            if definition is not None:
                groups.append(definition)
            else:
                warn(f"private rule references missing group '{ref}'")
        tagged_rules = [("default", line) for line in legacy]

    if tag is not None:
        tagged_rules = [(t, line) for t, line in tagged_rules if t == tag]
        if not tagged_rules:
            raise RuntimeError(f"no private rules with tag '{tag}'")

    # Ensure every referenced group has a definition line.
    known_group_names = {name for name, _, _ in groups}
    for ref in sorted(rule_refs([line for _, line in tagged_rules])
                      - public_group_names() - BUILTIN_GROUPS):
        if ref in known_group_names:
            continue
        definition = group_def_from_db(conn, ref)
        if definition is not None:
            groups.append(definition)
            known_group_names.add(ref)
        else:
            warn(f"private rule references missing group '{ref}'")

    return block_from_parts(groups, tagged_rules)


def insert_block(routing: str, block: str) -> str:
    start = routing.find(MARKER_START)
    end = routing.find(MARKER_END)
    if start != -1 and end != -1 and end > start:
        # `end` points at MARKER_END; skip the newline that terminates its
        # line so the replacement keeps exactly one line break of its own.
        return routing[:start] + block.rstrip("\n") + "\n" + routing[end + len(MARKER_END) + 1:]

    anchor = None
    for needle in ("# Geo-based routing", "fallback:"):
        pos = routing.find("\n" + needle)
        if pos != -1:
            anchor = pos
            break
    if anchor is None:
        # Insert before the closing brace of the routing section.
        pos = routing.rfind("}")
        anchor = pos if pos != -1 else len(routing)
        return routing[:anchor] + "\n" + block.rstrip("\n") + "\n" + routing[anchor:]
    return routing[:anchor] + "\n" + block.rstrip("\n") + "\n" + routing[anchor:]


def upsert_group(
    conn: sqlite3.Connection,
    name: str,
    policy: str,
    param: str,
    force: bool,
) -> None:
    if policy not in VALID_POLICIES:
        raise RuntimeError(f"group '{name}' has invalid policy '{policy}'")

    row = conn.execute("SELECT id, policy FROM groups WHERE name = ? LIMIT 1", (name,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO groups (name, policy, version) VALUES (?, ?, 0)", (name, policy)
        )
        gid = conn.execute("SELECT id FROM groups WHERE name = ?", (name,)).fetchone()[0]
        if policy == "fixed":
            idx = param if param.isdigit() else "0"
            conn.execute(
                "INSERT INTO group_policy_params (key, value, group_id) VALUES ('', ?, ?)",
                (idx, gid),
            )
        ok(f"created private group {name} (policy={policy})")
        return

    gid, old_policy = row
    if not force:
        info(f"keep existing group {name} (policy={old_policy})")
        return

    if old_policy != policy:
        conn.execute(
            "UPDATE groups SET policy = ?, version = version + 1 WHERE id = ?",
            (policy, gid),
        )
        ok(f"updated group {name} policy ({old_policy} -> {policy})")
    else:
        info(f"group {name} already has policy {policy}")

    if policy == "fixed":
        idx = param if param.isdigit() else "0"
        existing = conn.execute(
            "SELECT value FROM group_policy_params WHERE group_id = ? AND key = '' LIMIT 1",
            (gid,),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO group_policy_params (key, value, group_id) VALUES ('', ?, ?)",
                (idx, gid),
            )
        elif existing[0] != idx:
            conn.execute(
                "UPDATE group_policy_params SET value = ? WHERE group_id = ? AND key = ''",
                (idx, gid),
            )
            conn.execute("UPDATE groups SET version = version + 1 WHERE id = ?", (gid,))


def import_private(conn: sqlite3.Connection, block: str, force_groups: bool) -> None:
    groups, tagged_rules = block_to_parts(block)

    # Derive group definitions for referenced non-public groups when the
    # import file does not carry an explicit `# private-group:` line.
    known_group_names = {name for name, _, _ in groups}
    public_names = public_group_names()
    for ref in sorted(rule_refs([line for _, line in tagged_rules])
                      - public_names - BUILTIN_GROUPS):
        if ref in known_group_names:
            continue
        definition = group_def_from_db(conn, ref)
        if definition is not None:
            groups.append(definition)
            known_group_names.add(ref)
        else:
            raise RuntimeError(
                f"rule references group '{ref}', but it is neither public nor "
                "declared with `# private-group:` in the import file"
            )

    for name, policy, param in groups:
        upsert_group(conn, name, policy, param, force_groups)

    row = selected_routing(conn)
    if row is None:
        raise RuntimeError("routings table is empty; run `daed-init.py` first")

    routing_id, routing = row
    updated = insert_block(routing, block)
    if updated == routing:
        info("routing already contains the same private block")
        return

    conn.execute(
        "UPDATE routings SET routing = ?, version = version + 1 WHERE id = ?",
        (updated, routing_id),
    )
    ok("updated routing with private-rules block")


# ── commands ────────────────────────────────────────────────────────────────

def cmd_init(args: argparse.Namespace) -> int:
    if not wait_for_db():
        return fail(
            "wing.db not found. Start daed once first:\n"
            "  docker compose up -d daed"
        )

    ensure_global_conf()
    global_conf = CONFIG_DIR / "global.conf"
    if not global_conf.is_file():
        return fail("config/global.conf is missing and could not be generated")
    if "<YOUR_LAN_INTERFACE>" in global_conf.read_text(encoding="utf-8"):
        return fail(
            "could not auto-detect lan_interface; edit config/global.conf "
            "and set lan_interface before running init"
        )

    conn = sqlite3.connect(str(DB_PATH))
    try:
        seeded_any = False
        seeded_any |= seed_config(conn, "configs", "global", "global",
                                  CONFIG_DIR / "global.conf")
        seeded_any |= seed_config(conn, "dns", "dns", "dns",
                                  CONFIG_DIR / "dns.conf")
        seeded_any |= seed_config(conn, "routings", "routing", "routing",
                                  CONFIG_DIR / "routing.conf")
        seeded_any |= seed_groups(conn, CONFIG_DIR / "groups.txt")
        conn.commit()

        if seeded_any:
            ok("initialization complete. Restart daed to apply:")
            print("  docker restart daed")
        else:
            info("already initialized; nothing changed. The Web UI is the source of truth.")
        migration_notice()
        return 0
    except sqlite3.Error as exc:
        conn.rollback()
        return fail(str(exc))
    finally:
        conn.close()


def cmd_export_private(args: argparse.Namespace) -> int:
    db = Path(args.db) if args.db else DB_PATH
    if not db.is_file():
        return fail(f"wing.db not found at {db}")
    conn = sqlite3.connect(str(db))
    try:
        block = export_private(conn, args.tag)
    except RuntimeError as exc:
        return fail(str(exc))
    finally:
        conn.close()

    if args.output:
        Path(args.output).write_text(block, encoding="utf-8")
        ok(f"wrote private rules to {args.output}")
    else:
        sys.stdout.write(block)
    return 0


def cmd_import_private(args: argparse.Namespace) -> int:
    db = Path(args.db) if args.db else DB_PATH
    if not db.is_file():
        return fail(f"wing.db not found at {db}")
    if not args.file:
        return fail("import-private requires --file <path> (use '-' for stdin)")

    if args.file == "-":
        text = sys.stdin.read()
    else:
        path = Path(args.file)
        if not path.is_file():
            return fail(f"import file not found: {path}")
        text = path.read_text(encoding="utf-8")

    text = text.strip()
    if MARKER_START not in text or MARKER_END not in text:
        # Accept a plain rule list; wrap it as one default-tag block.
        rules = [line for line in text.splitlines() if line.strip()]
        text = block_from_parts([], [(None, line) for line in rules])

    conn = sqlite3.connect(str(db))
    try:
        import_private(conn, text, args.force_groups)
        conn.commit()
    except (sqlite3.Error, RuntimeError) as exc:
        conn.rollback()
        return fail(str(exc))
    finally:
        conn.close()

    ok("import complete. Restart daed to apply:")
    print("  docker restart daed")
    migration_notice()
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="daed one-shot bootstrap and private-rules migration")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="initialize an empty wing.db (default)")
    p_init.set_defaults(func=cmd_init)

    p_export = sub.add_parser("export-private", help="export private rules block from wing.db")
    p_export.add_argument("--output", help="write to file instead of stdout")
    p_export.add_argument("--tag", help="only export rules with this private-tag")
    p_export.add_argument("--db", help="wing.db path (default: deploy/daed/config/wing.db)")
    p_export.set_defaults(func=cmd_export_private)

    p_import = sub.add_parser("import-private", help="import private rules block into wing.db")
    p_import.add_argument("--file", required=True, help="file containing the private block ('-' for stdin)")
    p_import.add_argument("--force-groups", action="store_true", help="update existing private group policy/param")
    p_import.add_argument("--db", help="wing.db path (default: deploy/daed/config/wing.db)")
    p_import.set_defaults(func=cmd_import_private)

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    if args.command is None:
        args = parser.parse_args(["init"])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
