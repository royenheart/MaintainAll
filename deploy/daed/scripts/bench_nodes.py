#!/usr/bin/env python3
"""
Bench daed proxy group health + current egress throughput via gost.

Usage:
    python3 bench_nodes.py
    python3 bench_nodes.py --health-only
    python3 bench_nodes.py --throughput-only
    python3 bench_nodes.py --proxy http://127.0.0.1:20171
    DAED_USER=admin DAED_PASS=secret python3 bench_nodes.py

Health: GraphQL lists proxy-group nodes; docker logs supply ALIVE / latency.
Throughput: download via gost (current selected dialer), Cloudflare + GitHub.
Does NOT change group policy or pin nodes.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
DAED_DIR = SCRIPT_DIR.parent
DEFAULT_DB = DAED_DIR / "config" / "wing.db"
DEFAULT_GQL = "http://127.0.0.1:2023/graphql"
DEFAULT_PROXY = "http://127.0.0.1:20171"
DEFAULT_CONTAINER = "daed"
DEFAULT_GROUP = "proxy"
DEFAULT_LOG_SINCE = "30m"

# Cloudflare official speed endpoint (1 MiB)
CF_URL = "https://speed.cloudflare.com/__down?bytes=1048576"
# GitHub official public raw file (small, stable)
GH_URL = "https://raw.githubusercontent.com/github/gitignore/main/Python.gitignore"

RE_ALIVE = re.compile(
    r'\[(?P<from>ALIVE|NOT ALIVE)\s+--(?P<net>[^\]-]+)->\s*(?P<to>ALIVE|NOT ALIVE)\]".*?'
    r'dialer="(?P<dialer>[^"]+)".*?group=(?P<group>\S+)'
)
RE_ALIVE_ALT = re.compile(
    r'msg="\[(?P<from>ALIVE|NOT ALIVE)\s+--(?P<net>[^\]-]+)->\s*(?P<to>ALIVE|NOT ALIVE)\]"\s+'
    r'dialer="(?P<dialer>[^"]+)"\s+group=(?P<group>\S+)'
)
RE_SELECT = re.compile(
    r'msg="Group (?:re-)?selects dialer".*?_?(?:new_)?dialer="(?P<dialer>[^"]+)".*?'
    r'group=(?P<group>\S+).*?network=(?P<net>\S+)'
)
RE_SELECT_SIMPLE = re.compile(
    r'msg="Group selects dialer"\s+dialer="(?P<dialer>[^"]+)"\s+'
    r'group=(?P<group>\S+)\s+network=(?P<net>\S+)'
)
RE_NO_ALIVE = re.compile(
    r'msg="Group has no dialer alive"\s+group=(?P<group>\S+)\s+network=(?P<net>\S+)'
)
RE_GROUP_DUMP = re.compile(
    r"Group '(?P<group>[^']+)' \[(?P<net>[^\]]+)\]:\s*\n"
    r"(?P<body>(?:[^\n]*\n)*)",
    re.MULTILINE,
)
RE_DUMP_LINE = re.compile(
    r"^\s*\d+\.\s*\[.*?\]\s*(?P<name>.+?):\s*(?P<lat>\d+)ms\s*$"
)
RE_MOVING_AVG = re.compile(r"min_moving_avg=(?P<lat>\d+)ms")


@dataclass
class NodeInfo:
    id: str = ""
    name: str = ""
    protocol: str = ""
    address: str = ""
    tag: str = ""


@dataclass
class DialerHealth:
    name: str
    networks: dict[str, str] = field(default_factory=dict)  # net -> ALIVE|NOT ALIVE
    latency_ms: dict[str, int] = field(default_factory=dict)  # net -> ms
    selected: set[str] = field(default_factory=set)  # networks where selected
    last_event: str = ""


def gql(
    endpoint: str,
    query: str,
    token: str = "",
    timeout: float = 10.0,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps({"query": query}).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def db_username(db_path: Path) -> str:
    if not db_path.is_file():
        return ""
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT username FROM users LIMIT 1").fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception:
        return ""


def login(endpoint: str, user: str, password: str) -> str:
    q = (
        "{ token(username: "
        + json.dumps(user)
        + ", password: "
        + json.dumps(password)
        + ") }"
    )
    data = gql(endpoint, q)
    token = (data.get("data") or {}).get("token") or ""
    if not token:
        errs = data.get("errors") or []
        msg = errs[0].get("message", "login failed") if errs else "login failed"
        raise RuntimeError(msg)
    return token


def fetch_group_nodes(
    endpoint: str, token: str, group: str
) -> tuple[str, list[NodeInfo]]:
    """Return (policy, nodes) for a named group."""
    q = (
        "{ group(name: "
        + json.dumps(group)
        + ") { id name policy "
        "nodes { edges { id name protocol address tag } } "
        "subscriptions { id tag nodes { edges { id name protocol address tag } } } "
        "} }"
    )
    data = gql(endpoint, q, token=token)
    g = (data.get("data") or {}).get("group")
    if not g:
        errs = data.get("errors") or []
        msg = errs[0].get("message", "group not found") if errs else "group not found"
        raise RuntimeError(msg)

    seen: set[str] = set()
    nodes: list[NodeInfo] = []

    def add_edges(edges: list[dict] | None) -> None:
        for e in edges or []:
            nid = e.get("id") or ""
            if nid in seen:
                continue
            seen.add(nid)
            nodes.append(
                NodeInfo(
                    id=nid,
                    name=e.get("name") or "",
                    protocol=e.get("protocol") or "",
                    address=e.get("address") or "",
                    tag=e.get("tag") or "",
                )
            )

    add_edges(((g.get("nodes") or {}).get("edges")) or [])
    for sub in g.get("subscriptions") or []:
        add_edges(((sub.get("nodes") or {}).get("edges")) or [])

    return g.get("policy") or "", nodes


def docker_logs(container: str, since: str) -> str:
    try:
        out = subprocess.run(
            ["docker", "logs", container, f"--since={since}"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError("docker not found in PATH") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("docker logs timed out") from e
    # daed logs go to stderr
    return (out.stdout or "") + (out.stderr or "")


def parse_health(logs: str, group: str) -> dict[str, DialerHealth]:
    """Parse ALIVE transitions, selections, and latency dumps in log order."""
    by_name: dict[str, DialerHealth] = {}

    def get(name: str) -> DialerHealth:
        name = name.strip()
        if name not in by_name:
            by_name[name] = DialerHealth(name=name)
        return by_name[name]

    # Join multi-line msg payloads that embed newlines inside the quoted msg=
    # Keep it simple: scan line-by-line; dump body often appears on next lines.
    pending_dump: tuple[str, str] | None = None  # (group, net)

    for line in logs.splitlines():
        if pending_dump:
            pg, pnet = pending_dump
            dm = RE_DUMP_LINE.match(line.strip().rstrip('"')) or re.match(
                r'^\s*\d+\.\s*\[.*?\]\s*(?P<name>.+?):\s*(?P<lat>\d+)ms',
                line,
            )
            if dm and pg == group:
                d = get(dm.group("name"))
                d.latency_ms[pnet] = int(dm.group("lat"))
                d.networks[pnet] = "ALIVE"
                continue
            pending_dump = None

        m = RE_ALIVE_ALT.search(line) or RE_ALIVE.search(line)
        if m and m.group("group").strip('"') == group:
            net = m.group("net").strip()
            d = get(m.group("dialer"))
            d.networks[net] = m.group("to")
            d.last_event = f"{m.group('from')}->{m.group('to')} ({net})"
            continue

        m = RE_SELECT_SIMPLE.search(line) or RE_SELECT.search(line)
        if m and m.group("group").strip('"') == group:
            net = m.group("net").strip().strip('"')
            d = get(m.group("dialer"))
            d.selected.add(net)
            d.networks[net] = "ALIVE"
            avg = RE_MOVING_AVG.search(line)
            if avg:
                d.latency_ms[net] = int(avg.group("lat"))
            continue

        dm_hdr = re.search(
            r"Group '(?P<group>[^']+)' \[(?P<net>[^\]]+)\]:", line
        )
        if dm_hdr:
            pending_dump = (dm_hdr.group("group"), dm_hdr.group("net"))
            # same-line body?
            rest = line.split("]:", 1)[-1]
            dm = re.search(
                r"(\d+)\.\s*\[.*?\]\s*(?P<name>.+?):\s*(?P<lat>\d+)ms", rest
            )
            if dm and pending_dump[0] == group:
                d = get(dm.group("name"))
                d.latency_ms[pending_dump[1]] = int(dm.group("lat"))
                d.networks[pending_dump[1]] = "ALIVE"
                pending_dump = None
            continue

    return by_name


def summarize_status(h: DialerHealth) -> str:
    # Prefer IPv4; do not let IPv6-only failures hide a working tcp4 dialer
    for key in ("tcp4", "tcp4(DNS)", "udp4(DNS)"):
        if key in h.networks:
            return h.networks[key]
    v4_keys = [k for k in h.networks if "6" not in k]
    if v4_keys:
        if any(h.networks[k] == "ALIVE" for k in v4_keys):
            return "ALIVE"
        return "NOT ALIVE"
    if any(v == "ALIVE" for v in h.networks.values()):
        return "ALIVE(v6)"
    if h.latency_ms or h.selected:
        return "ALIVE"
    if h.networks:
        return "NOT ALIVE"
    return "unknown"


def best_latency(h: DialerHealth) -> str:
    for key in ("tcp4", "tcp4(DNS)", "udp4(DNS)"):
        if key in h.latency_ms:
            return f"{h.latency_ms[key]}ms"
    if h.latency_ms:
        k = next(iter(h.latency_ms))
        return f"{h.latency_ms[k]}ms({k})"
    return "-"


def match_health(name: str, health: dict[str, DialerHealth]) -> DialerHealth | None:
    if name in health:
        return health[name]
    # dialer names in logs often prefixed like "1.iGG-..."
    for k, v in health.items():
        if k.endswith(name) or name in k or k in name:
            return v
    return None


def print_health_table(
    nodes: list[NodeInfo],
    health: dict[str, DialerHealth],
    policy: str,
    group: str,
) -> None:
    print(f"\n=== Health: group={group} policy={policy or '?'} ===")
    headers = ("NAME", "PROTO", "STATUS", "LATENCY", "SELECTED", "NOTE")
    rows: list[tuple[str, ...]] = []

    used: set[str] = set()
    for n in nodes:
        h = match_health(n.name, health)
        if h:
            used.add(h.name)
        status = summarize_status(h) if h else "unknown"
        lat = best_latency(h) if h else "-"
        sel = ",".join(sorted(h.selected)) if h and h.selected else "-"
        note = h.last_event if h else "no recent log"
        rows.append((n.name or n.id, n.protocol or "-", status, lat, sel, note))

    # orphan dialers seen in logs but not in GraphQL list
    for name, h in sorted(health.items()):
        if name in used:
            continue
        rows.append(
            (
                name,
                "-",
                summarize_status(h),
                best_latency(h),
                ",".join(sorted(h.selected)) or "-",
                h.last_event or "log-only",
            )
        )

    if not rows:
        print("(no nodes / no health events in log window)")
        return

    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], min(len(c), 48))

    def fmt(cols: tuple[str, ...]) -> str:
        parts = []
        for i, c in enumerate(cols):
            text = c if len(c) <= widths[i] else c[: widths[i] - 1] + "…"
            parts.append(text.ljust(widths[i]))
        return "  ".join(parts)

    print(fmt(headers))
    print(fmt(tuple("-" * w for w in widths)))
    for r in rows:
        print(fmt(r))

    # no-alive summary from last logs is already in STATUS column


def download_via_proxy(
    url: str,
    proxy: str,
    timeout: float,
) -> dict[str, Any]:
    """Download url through HTTP/HTTPS proxy; return metrics."""
    handlers = [
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
        urllib.request.HTTPSHandler(),
    ]
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "daed-bench_nodes/1.0"},
        method="GET",
    )
    t0 = time.perf_counter()
    try:
        with opener.open(req, timeout=timeout) as resp:
            chunks = []
            while True:
                buf = resp.read(64 * 1024)
                if not buf:
                    break
                chunks.append(buf)
            body = b"".join(chunks)
            elapsed = time.perf_counter() - t0
            size = len(body)
            speed = size / elapsed if elapsed > 0 else 0.0
            return {
                "ok": True,
                "http": getattr(resp, "status", 200),
                "bytes": size,
                "seconds": elapsed,
                "kb_s": speed / 1024.0,
                "error": "",
            }
    except Exception as e:
        elapsed = time.perf_counter() - t0
        code = ""
        if isinstance(e, urllib.error.HTTPError):
            code = str(e.code)
        return {
            "ok": False,
            "http": code or "-",
            "bytes": 0,
            "seconds": elapsed,
            "kb_s": 0.0,
            "error": str(e),
        }


def print_throughput(proxy: str, timeout: float) -> int:
    """Run throughput tests; return number of failures."""
    print(f"\n=== Throughput via {proxy} (current selected dialer) ===")
    targets = (
        ("Cloudflare 1MiB", CF_URL),
        ("GitHub raw (gitignore)", GH_URL),
    )
    fails = 0
    for label, url in targets:
        print(f"\n→ {label}")
        print(f"  {url}")
        r = download_via_proxy(url, proxy, timeout)
        if r["ok"]:
            print(
                f"  OK  http={r['http']}  bytes={r['bytes']}  "
                f"time={r['seconds']:.2f}s  speed={r['kb_s']:.1f} KiB/s"
            )
        else:
            fails += 1
            print(
                f"  FAIL  http={r['http']}  time={r['seconds']:.2f}s  "
                f"error={r['error']}"
            )
    return fails


def resolve_credentials(args: argparse.Namespace) -> tuple[str, str]:
    user = args.user or os.environ.get("DAED_USER", "")
    password = args.password or os.environ.get("DAED_PASS", "")
    if not user:
        user = db_username(Path(args.db))
    if not user:
        user = input("daed username: ").strip()
    if not password:
        password = getpass.getpass(f"daed password for '{user}': ")
    return user, password


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Bench daed proxy health (logs) + egress throughput (gost)."
    )
    p.add_argument("--health-only", action="store_true", help="Only parse node health")
    p.add_argument(
        "--throughput-only", action="store_true", help="Only run download benchmarks"
    )
    p.add_argument("--endpoint", default=DEFAULT_GQL, help="GraphQL endpoint")
    p.add_argument("--proxy", default=DEFAULT_PROXY, help="HTTP proxy (gost)")
    p.add_argument("--container", default=DEFAULT_CONTAINER, help="daed container name")
    p.add_argument("--group", default=DEFAULT_GROUP, help="Outbound group name")
    p.add_argument("--since", default=DEFAULT_LOG_SINCE, help="docker logs --since")
    p.add_argument("--timeout", type=float, default=30.0, help="Download timeout (s)")
    p.add_argument("--db", default=str(DEFAULT_DB), help="wing.db path (username hint)")
    p.add_argument("--user", default="", help="daed username (or DAED_USER)")
    p.add_argument("--password", default="", help="daed password (or DAED_PASS)")
    p.add_argument(
        "--skip-graphql",
        action="store_true",
        help="Skip GraphQL; health from logs only",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    do_health = not args.throughput_only
    do_tp = not args.health_only
    if args.health_only and args.throughput_only:
        print("Error: --health-only and --throughput-only are mutually exclusive")
        return 2

    # API readiness
    try:
        hc = gql(args.endpoint, "{ healthCheck }")
        if (hc.get("data") or {}).get("healthCheck") != 1:
            print(f"Warning: healthCheck unexpected: {hc}")
    except Exception as e:
        print(f"Error: cannot reach daed GraphQL at {args.endpoint}: {e}")
        if do_health and not args.skip_graphql:
            print("Hint: use --skip-graphql to parse logs only, or start daed.")
            if not do_tp:
                return 1

    nodes: list[NodeInfo] = []
    policy = ""
    if do_health and not args.skip_graphql:
        try:
            user, password = resolve_credentials(args)
            token = login(args.endpoint, user, password)
            policy, nodes = fetch_group_nodes(args.endpoint, token, args.group)
            print(f"GraphQL: {len(nodes)} node(s) in group '{args.group}'")
        except Exception as e:
            print(f"Warning: GraphQL node list failed: {e}")
            print("Continuing with log-only health parse.")

    health: dict[str, DialerHealth] = {}
    if do_health:
        try:
            logs = docker_logs(args.container, args.since)
            health = parse_health(logs, args.group)
            print(
                f"Logs: parsed {len(health)} dialer(s) from "
                f"{args.container} --since {args.since}"
            )
        except Exception as e:
            print(f"Error: reading docker logs: {e}")
            if not do_tp:
                return 1
        print_health_table(nodes, health, policy, args.group)

    fails = 0
    if do_tp:
        fails = print_throughput(args.proxy, args.timeout)

    print()
    if fails:
        print(f"Done with {fails} throughput failure(s).")
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
