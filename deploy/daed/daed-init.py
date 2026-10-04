#!/usr/bin/env python3
"""One-shot bootstrap + private-rules migration for daed.

Usage:
    python3 daed-init.py                        # initialize an empty wing.db (once)
    python3 daed-init.py init --dns-mode doh    # same, but seed the foreign DoH mode
    python3 daed-init.py dns-mode status        # show the selected DNS mode
    python3 daed-init.py dns-mode doh           # switch an existing wing.db to DoH
    python3 daed-init.py dns-mode direct        # switch it back
    python3 daed-init.py export-private         # print the private rules block from wing.db
    python3 daed-init.py export-private --tag work --output private.txt
    python3 daed-init.py import-private --file private.txt [--force-groups]

`init` only writes when the corresponding table is empty, so it can never
overwrite changes made in the daed Web UI. The Web UI is the source of truth
after initialization.

`dns-mode` is the only command that edits an already-seeded library. It copies
wing.db to a backup, then in one transaction updates the selected DNS row,
that row's global `fallback_resolver`, and the `systemd-resolved` must_direct
rule. Nodes, groups, and every other routing line stay as they are.

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

# direct: domestic UDP + foreign tcp+udp/53, systemd-resolved stays must_direct.
# doh: foreign queries use an IP-literal DoH URL; systemd-resolved enters daed.
DNS_MODES = ("direct", "doh")
DOH_IPS = ("8.8.8.8", "1.1.1.1")
DIRECT_FALLBACK = "223.5.5.5:53"
RESOLVED_NAME = "systemd-resolved"
_FALLBACK_RE = re.compile(
    r"^(?P<indent>[ \t]*)fallback_resolver[ \t]*:[ \t]*(?P<quote>[\"']?)"
    r"(?P<value>[^\"'\s#]+)(?P=quote)[ \t]*$",
    re.M,
)
_PNAME_LINE = re.compile(r"^(\s*)pname\(([^)]*)\)\s*->\s*must_direct\s*$")
_RESOLVER_PNAME = {"NetworkManager", RESOLVED_NAME, "dnsmasq"}

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

def wait_for_db(timeout: float = 30.0, db: Path | None = None) -> bool:
    path = DB_PATH if db is None else db
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.is_file():
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


# ── DNS modes ───────────────────────────────────────────────────────────────

def choose_dns_mode() -> str:
    """Ask which DNS mode to seed. Non-interactive runs stay on direct."""
    if not (hasattr(sys.stdin, "isatty") and sys.stdin.isatty()):
        info("non-interactive run; DNS mode: direct")
        return "direct"
    print()
    print(paint("选择 DNS 模式（回车 = direct）", C.CYAN))
    print("  1. direct  国内域名走 223.5.5.5 UDP，其余走 tcp+udp://8.8.8.8:53。")
    print("             systemd-resolved 不进 daed。")
    print("  2. doh     国外域名走 https://8.8.8.8/dns-query。")
    print("             systemd-resolved 的 53 端口查询进 daed。")
    try:
        answer = input("选择 [1]: ").strip().lower()
    except EOFError:
        print()
        return "direct"
    print()
    if answer in {"2", "doh"}:
        return "doh"
    return "direct"


def fallback_value(mode: str, doh_ip: str) -> str:
    if mode == "direct":
        return DIRECT_FALLBACK
    if doh_ip not in DOH_IPS:
        raise ValueError(f"unsupported DoH address: {doh_ip}")
    return f"{doh_ip}:53"


def render_dns_body(mode: str, doh_ip: str) -> str:
    if mode == "direct":
        return (CONFIG_DIR / "dns.conf").read_text(encoding="utf-8")
    if doh_ip not in DOH_IPS:
        raise ValueError(f"unsupported DoH address: {doh_ip}")
    text = (CONFIG_DIR / "dns.conf.foreign-doh").read_text(encoding="utf-8")
    if doh_ip != "8.8.8.8":
        text = text.replace(
            "https://8.8.8.8/dns-query", f"https://{doh_ip}/dns-query"
        )
    return text


def set_fallback_resolver(text: str, value: str) -> str:
    """Replace fallback_resolver, preserving the line's quotes and spacing."""
    match = _FALLBACK_RE.search(text)
    if match is None:
        line = f'fallback_resolver: "{value}"\n'
        closing = text.rfind("}")
        if closing == -1:
            return text.rstrip() + "\n" + line
        return text[:closing] + line + text[closing:]
    raw = match.group(0)
    colon = ": " if re.search(r":[ \t]", raw) else ":"
    quote = match.group("quote") or '"'
    replacement = f"{match.group('indent')}fallback_resolver{colon}{quote}{value}{quote}"
    return text[:match.start()] + replacement + text[match.end():]


def _split_pname(body: str) -> list[str]:
    return [part.strip() for part in body.split(",") if part.strip()]


def _resolver_line_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        match = _PNAME_LINE.match(line.rstrip("\r\n"))
        if match is None:
            continue
        names = set(_split_pname(match.group(2)))
        if names & _RESOLVER_PNAME:
            return index
    return None


def set_systemd_resolved(routing: str, enter_daed: bool) -> str:
    """Drop or restore systemd-resolved on the local-resolver must_direct rule.

    enter_daed=True removes the name so its port 53 queries hit daed.
    Other routing lines, including private rules, are left in place.
    """
    lines = routing.splitlines(keepends=True)
    index = _resolver_line_index(lines)
    if enter_daed:
        if index is None:
            return routing
        stripped = lines[index].rstrip("\r\n")
        newline = lines[index][len(stripped):]
        match = _PNAME_LINE.match(stripped)
        assert match is not None
        names = [name for name in _split_pname(match.group(2)) if name != RESOLVED_NAME]
        if names == _split_pname(match.group(2)):
            return routing
        if not names:
            del lines[index]
        else:
            lines[index] = (
                f"{match.group(1)}pname({', '.join(names)}) -> must_direct{newline}"
            )
        return "".join(lines)

    if index is not None:
        stripped = lines[index].rstrip("\r\n")
        newline = lines[index][len(stripped):]
        match = _PNAME_LINE.match(stripped)
        assert match is not None
        names = _split_pname(match.group(2))
        if RESOLVED_NAME in names:
            return routing
        if "NetworkManager" in names:
            names.insert(names.index("NetworkManager") + 1, RESOLVED_NAME)
        else:
            names.insert(0, RESOLVED_NAME)
        lines[index] = (
            f"{match.group(1)}pname({', '.join(names)}) -> must_direct{newline}"
        )
        return "".join(lines)

    insert = "pname(NetworkManager, systemd-resolved, dnsmasq) -> must_direct\n"
    for index, line in enumerate(lines):
        if "pname(daed)" in line:
            lines.insert(index + 1, insert)
            return "".join(lines)
    for index, line in enumerate(lines):
        if line.strip() == "routing {":
            lines.insert(index + 1, insert)
            return "".join(lines)
    return insert + routing


def _fallback_of(text: str) -> str | None:
    match = _FALLBACK_RE.search(text)
    if match is None:
        return None
    return match.group("value")


def _resolved_is_direct(routing: str) -> bool:
    for line in routing.splitlines():
        match = _PNAME_LINE.match(line.rstrip())
        if match and RESOLVED_NAME in _split_pname(match.group(2)):
            return True
    return False


def already_in_mode(dns: str, global_text: str, routing: str, mode: str, doh_ip: str) -> bool:
    """True when the live texts already have this mode's upstream, fallback, and resolver rule.

    Whitespace and unrelated DNS lines do not count, so a daed rewrite of the
    same mode is left alone.
    """
    fallback = _fallback_of(global_text)
    resolved_direct = _resolved_is_direct(routing)
    has_tcp = "tcp+udp://8.8.8.8:53" in dns
    has_doh = f"https://{doh_ip}/dns-query" in dns
    has_any_foreign_doh = any(f"https://{ip}/dns-query" in dns for ip in DOH_IPS)
    if mode == "doh":
        return has_doh and not has_tcp and fallback == f"{doh_ip}:53" and not resolved_direct
    return (
        has_tcp
        and not has_any_foreign_doh
        and fallback == DIRECT_FALLBACK
        and resolved_direct
    )


def apply_mode_to_sections(
    dns: str, global_text: str, routing: str, mode: str, doh_ip: str
) -> tuple[str, str, str]:
    del dns  # the selected DNS row is replaced by the mode template
    new_dns = wrap_section("dns", render_dns_body(mode, doh_ip))
    new_global = set_fallback_resolver(global_text, fallback_value(mode, doh_ip))
    new_routing = set_systemd_resolved(routing, enter_daed=(mode == "doh"))
    return new_dns, new_global, new_routing


def describe_dns_mode(dns: str, global_text: str, routing: str) -> str:
    if "https://1.1.1.1/dns-query" in dns:
        upstream = "doh https://1.1.1.1/dns-query"
    elif "https://8.8.8.8/dns-query" in dns:
        upstream = "doh https://8.8.8.8/dns-query"
    elif "tcp+udp://8.8.8.8:53" in dns:
        upstream = "direct tcp+udp://8.8.8.8:53"
    else:
        upstream = "custom"
    fallback = _fallback_of(global_text) or "missing"
    resolved = "must_direct" if _resolved_is_direct(routing) else "enters daed"
    return f"dns={upstream} fallback_resolver={fallback} systemd-resolved={resolved}"


def _connect(path: Path, timeout: float, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=timeout)
    return sqlite3.connect(str(path), timeout=timeout)


def _selected_text(conn: sqlite3.Connection, table: str, column: str) -> tuple[int, str] | None:
    quoted = f'"{column}"'
    row = conn.execute(
        f"SELECT id, {quoted} FROM {table} WHERE selected = 1 LIMIT 1"
    ).fetchone()
    if row is None:
        row = conn.execute(
            f"SELECT id, {quoted} FROM {table} ORDER BY id LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return int(row[0]), row[1]


def _locked_message(exc: sqlite3.OperationalError) -> str:
    text = str(exc).lower()
    if "locked" in text or "busy" in text:
        return (
            "wing.db is locked by daed (database is locked). "
            "Nothing was written. Retry in a moment."
        )
    return str(exc)


def _read_mode_rows(conn: sqlite3.Connection) -> tuple[tuple[int, str], tuple[int, str], tuple[int, str]]:
    dns_row = _selected_text(conn, "dns", "dns")
    global_row = _selected_text(conn, "configs", "global")
    routing_row = _selected_text(conn, "routings", "routing")
    if dns_row is None or global_row is None or routing_row is None:
        raise RuntimeError(
            "dns, configs, or routings is empty; run python3 daed-init.py first"
        )
    return dns_row, global_row, routing_row


def backup_wing_db(src: Path, timeout: float) -> Path:
    """Consistent snapshot via SQLite's backup API. A plain copy can tear a WAL."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = src.with_name(f"{src.name}.bak-{stamp}")
    suffix = 2
    while dest.exists():
        dest = src.with_name(f"{src.name}.bak-{stamp}-{suffix}")
        suffix += 1
    src_conn = _connect(src, timeout, readonly=True)
    try:
        dest_conn = sqlite3.connect(dest, timeout=timeout)
        try:
            src_conn.backup(dest_conn)
            dest_conn.commit()
        finally:
            dest_conn.close()
    except sqlite3.OperationalError:
        dest.unlink(missing_ok=True)
        raise
    finally:
        src_conn.close()
    return dest


def apply_dns_mode(conn: sqlite3.Connection, mode: str, doh_ip: str) -> list[str]:
    """Update the selected DNS, fallback_resolver, and systemd-resolved lines.

    The caller owns the transaction. Nodes, groups, and other routing lines
    are not rewritten.
    """
    dns_row, global_row, routing_row = _read_mode_rows(conn)
    if already_in_mode(dns_row[1], global_row[1], routing_row[1], mode, doh_ip):
        return []
    new_dns, new_global, new_routing = apply_mode_to_sections(
        dns_row[1], global_row[1], routing_row[1], mode, doh_ip
    )
    changes: list[str] = []
    if new_dns != dns_row[1]:
        conn.execute(
            "UPDATE dns SET dns = ?, version = version + 1 WHERE id = ?",
            (new_dns, dns_row[0]),
        )
        changes.append("dns")
    if new_global != global_row[1]:
        conn.execute(
            'UPDATE configs SET "global" = ?, version = version + 1 WHERE id = ?',
            (new_global, global_row[0]),
        )
        changes.append("fallback_resolver")
    if new_routing != routing_row[1]:
        conn.execute(
            "UPDATE routings SET routing = ?, version = version + 1 WHERE id = ?",
            (new_routing, routing_row[0]),
        )
        changes.append("systemd-resolved")
    return changes


def switch_dns_mode(db: Path, mode: str, doh_ip: str = "8.8.8.8", timeout: float = 5.0) -> int:
    if mode not in (*DNS_MODES, "status"):
        return fail(f"unknown DNS mode: {mode}")
    if doh_ip not in DOH_IPS:
        return fail(f"unsupported DoH address: {doh_ip}")
    if not db.is_file():
        return fail(f"wing.db not found at {db}")

    try:
        preview = _connect(db, timeout, readonly=True)
    except sqlite3.OperationalError as exc:
        return fail(_locked_message(exc))
    try:
        dns_row, global_row, routing_row = _read_mode_rows(preview)
    except RuntimeError as exc:
        return fail(str(exc))
    except sqlite3.OperationalError as exc:
        return fail(_locked_message(exc))
    finally:
        preview.close()

    if mode == "status":
        print(describe_dns_mode(dns_row[1], global_row[1], routing_row[1]))
        return 0

    if already_in_mode(dns_row[1], global_row[1], routing_row[1], mode, doh_ip):
        info(f"already in {mode} mode; nothing changed")
        print(describe_dns_mode(dns_row[1], global_row[1], routing_row[1]))
        return 0

    try:
        backup = backup_wing_db(db, timeout)
    except sqlite3.OperationalError as exc:
        return fail(_locked_message(exc))
    ok(f"backed up wing.db to {backup.name}")

    conn = _connect(db, timeout)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            changes = apply_dns_mode(conn, mode, doh_ip)
            if not changes:
                conn.rollback()
                info(f"already in {mode} mode; nothing changed")
                return 0
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    except sqlite3.OperationalError as exc:
        return fail(_locked_message(exc) + f" Backup kept at {backup.name}.")
    except RuntimeError as exc:
        return fail(str(exc) + f" Backup kept at {backup.name}.")
    finally:
        conn.close()

    ok(f"switched to {mode}: {', '.join(changes)}")
    ok("selected DNS row was replaced with the mode template")
    ok("Restart daed to apply:")
    print("  docker restart daed")
    return 0


# ── init: config seeding ────────────────────────────────────────────────────

def seed_config(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    section: str,
    file: Path,
    text: str | None = None,
) -> bool:
    if not table_exists(conn, table):
        warn(f"skip {table}: table missing (daed not booted yet?)")
        return False

    if table_count(conn, table) > 0:
        info(f"skip {table}: already initialized")
        return False

    if text is None:
        if not file.is_file():
            warn(f"skip {table}: {file.name} not found")
            return False
        text = file.read_text(encoding="utf-8")

    content = wrap_section(section, text)
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
    db = Path(args.db) if getattr(args, "db", None) else DB_PATH
    if not wait_for_db(db=db):
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

    conn = sqlite3.connect(str(db))
    try:
        mode = "direct"
        doh_ip = getattr(args, "doh_ip", None) or "8.8.8.8"
        requested = getattr(args, "dns_mode", None)
        dns_empty = table_exists(conn, "dns") and table_count(conn, "dns") == 0
        if dns_empty:
            mode = requested or choose_dns_mode()
            info(f"DNS mode for empty dns table: {mode}")
        elif requested not in (None, "direct"):
            warn(
                "dns table already has rows; init does not switch modes. "
                f"Run: python3 daed-init.py dns-mode {requested}"
            )

        dns_file = CONFIG_DIR / "dns.conf"
        dns_text = global_text = routing_text = None
        if mode == "doh":
            dns_file = CONFIG_DIR / "dns.conf.foreign-doh"
            dns_text = render_dns_body("doh", doh_ip)
            global_text = set_fallback_resolver(
                global_conf.read_text(encoding="utf-8"),
                fallback_value("doh", doh_ip),
            )
            routing_text = set_systemd_resolved(
                (CONFIG_DIR / "routing.conf").read_text(encoding="utf-8"),
                enter_daed=True,
            )
            if table_exists(conn, "configs") and table_count(conn, "configs") > 0:
                warn("configs already has rows; init will not change fallback_resolver. Use dns-mode.")
            if table_exists(conn, "routings") and table_count(conn, "routings") > 0:
                warn("routings already has rows; init will not change systemd-resolved. Use dns-mode.")

        seeded_any = False
        seeded_any |= seed_config(conn, "configs", "global", "global",
                                  CONFIG_DIR / "global.conf", text=global_text)
        seeded_any |= seed_config(conn, "dns", "dns", "dns",
                                  dns_file, text=dns_text)
        seeded_any |= seed_config(conn, "routings", "routing", "routing",
                                  CONFIG_DIR / "routing.conf", text=routing_text)
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


def cmd_dns_mode(args: argparse.Namespace) -> int:
    db = Path(args.db) if args.db else DB_PATH
    return switch_dns_mode(db, args.mode, args.doh_ip)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="daed one-shot bootstrap and private-rules migration")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="initialize an empty wing.db (default)")
    p_init.add_argument(
        "--dns-mode", choices=list(DNS_MODES), default=None,
        help="DNS mode when the dns table is empty (default: direct, or a prompt on a TTY)",
    )
    p_init.add_argument(
        "--doh-ip", choices=list(DOH_IPS), default="8.8.8.8",
        help="foreign DoH address when --dns-mode doh",
    )
    p_init.add_argument("--db", help="wing.db path (default: deploy/daed/config/wing.db)")
    p_init.set_defaults(func=cmd_init)

    p_mode = sub.add_parser("dns-mode", help="show or switch DNS mode in an existing wing.db")
    p_mode.add_argument("mode", choices=[*DNS_MODES, "status"])
    p_mode.add_argument(
        "--doh-ip", choices=list(DOH_IPS), default="8.8.8.8",
        help="foreign DoH address for doh mode (default: 8.8.8.8)",
    )
    p_mode.add_argument("--db", help="wing.db path (default: deploy/daed/config/wing.db)")
    p_mode.set_defaults(func=cmd_dns_mode)

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
