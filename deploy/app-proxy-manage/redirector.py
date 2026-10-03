"""Per-app redirector used when Clash Verge TUN is not up.

A whitelisted process connects to the tray's loopback listener. The listener
opens the configured SOCKS5 connection and relays the bytes. The hook is loaded
only into those processes and their descendants, so any other process keeps the
normal connect path.

TCP is not diverted. WinDivert only discards UDP port 443 from the whitelisted
PIDs, which makes QUIC fall back to the hooked TCP connect. There is no
processId 0 filter. If a Mihomo TUN adapter is up, this backend stays idle.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_TUN_NAME_RE = re.compile(r"wintun|mihomo|clash", re.I)

NAT_IDLE_SECONDS = 120.0
RELAY_IDLE_SECONDS = 180.0
HANDSHAKE_LIMIT = 64
LISTEN_BACKLOG = 1024
_ANCESTOR_LIMIT = 16
_PID_REFRESH_SECONDS = 0.2
_TUN_CHECK_EVERY = 10

_DIRECT_V4 = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
)
_DIRECT_V6 = (
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("ff00::/8"),
)
_LOOPBACKS = frozenset({"127.0.0.1", "::1"})


def looks_like_tun(name: str) -> bool:
    return bool(_TUN_NAME_RE.search(name or ""))


def is_direct_ip(ip: str) -> bool:
    """True when the address must stay on the normal route.

    Global IPv6 is not direct: the installer chooses proxy or reject.
    Unparseable text stays direct so a bad packet is never captured.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    nets = _DIRECT_V4 if addr.version == 4 else _DIRECT_V6
    return any(addr in net for net in nets)


def normalize_ipv6_mode(mode: str | None) -> str:
    text = (mode or "").strip().lower()
    return text if text in ("reject", "proxy") else "reject"


def build_filter(
    pids: set[int],
    local_port: int = 0,
    local_v6: int = 0,
    ipv6_mode: str = "reject",
) -> str | None:
    """UDP port 443 for these PIDs only.

    TCP is intentionally absent. A process that is not listed, including one
    whose packets show up as processId 0, does not match. The listen-port
    arguments are ignored so they cannot widen the filter.
    """
    _ = (local_port, local_v6, ipv6_mode)
    if not pids:
        return None
    pid_clause = " or ".join(f"processId == {pid}" for pid in sorted(pids))
    return f"outbound and udp.DstPort == 443 and ({pid_clause})"


def should_capture_process(pid: int, allowed: set[int]) -> bool:
    """False for an unknown process id. Those packets stay on the normal route."""
    return pid > 0 and pid in allowed


def hook_action(ip: str, ipv6_mode: str) -> str:
    """How a whitelisted connect() is handled: original, redirect, or refuse.

    IPv4 is never refused. Refusal is only for global IPv6 when the installer
    selected reject, and it happens inside the process before a SYN is sent.
    """
    text = _flow_ip(ip)
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return "original"
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        return hook_action(str(mapped), ipv6_mode)
    if is_direct_ip(text):
        return "original"
    if addr.version == 6 and normalize_ipv6_mode(ipv6_mode) != "proxy":
        return "refuse"
    return "redirect"


def plan_upstream(ip: str, ipv6_mode: str) -> str:
    """socks, direct, or refuse. Public IPv4 is always socks."""
    action = hook_action(ip, ipv6_mode)
    if action == "redirect":
        return "socks"
    if action == "refuse":
        return "refuse"
    return "direct"


_PREAMBLE_MAGIC = b"MAC1"


def encode_connect_preamble(ip: str, port: int) -> bytes:
    """Bytes the hook writes after the loopback handshake."""
    addr = ipaddress.ip_address(_flow_ip(ip))
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        addr = mapped
    kind = 4 if addr.version == 4 else 6
    return _PREAMBLE_MAGIC + bytes((kind,)) + addr.packed + int(port).to_bytes(2, "big")


def read_connect_preamble(sock: socket.socket) -> tuple[str, int] | None:
    head = _recvn(sock, 5)
    if len(head) != 5 or head[:4] != _PREAMBLE_MAGIC:
        return None
    kind = head[4]
    if kind == 4:
        rest = _recvn(sock, 6)
        if len(rest) != 6:
            return None
        return str(ipaddress.IPv4Address(rest[:4])), int.from_bytes(rest[4:6], "big")
    if kind == 6:
        rest = _recvn(sock, 18)
        if len(rest) != 18:
            return None
        return str(ipaddress.IPv6Address(rest[:16])), int.from_bytes(rest[16:18], "big")
    return None


def open_redirected_upstream(
    client: socket.socket,
    socks_host: str,
    socks_port: int,
    ipv6_mode: str,
) -> socket.socket | None:
    """Finish the loopback handshake and return the upstream socket.

    The client is closed when the preamble or the upstream connect fails.
    """
    remote: socket.socket | None = None
    try:
        client.settimeout(10)
        parsed = read_connect_preamble(client)
        if parsed is None:
            client.close()
            return None
        ip, port = parsed
        if not 0 < port < 65536:
            client.close()
            return None
        action = plan_upstream(ip, ipv6_mode)
        if action == "refuse":
            client.close()
            return None
        if action == "direct":
            remote = socket.create_connection((ip, port), timeout=10)
        else:
            remote = socket.create_connection((socks_host, socks_port), timeout=10)
            socks5_connect(remote, ip, port)
        client.settimeout(None)
        return remote
    except OSError:
        try:
            client.close()
        except OSError:
            pass
        if remote is not None:
            try:
                remote.close()
            except OSError:
                pass
        return None


class FlowOwners:
    """Map a local socket to its PID. lookup() never reads the OS.

    A background thread refreshes the snapshot. The packet thread only reads
    the dict, so a processId 0 SYN is either redirected or reinjected at once.
    """

    def __init__(self, loader=None) -> None:
        self._loader = loader or load_flow_owners
        self._tcp: dict[tuple[str, int], int] = {}
        self._udp: dict[tuple[str, int], int] = {}
        self._lock = threading.Lock()

    def lookup(self, src: str, sport: int, proto: str) -> int:
        key = (_flow_ip(src), int(sport))
        with self._lock:
            table = self._udp if proto == "udp" else self._tcp
            return table.get(key, 0)

    def refresh(self) -> None:
        tcp, udp = self._loader()
        with self._lock:
            self._tcp = tcp
            self._udp = udp


def _is_loopback_addr(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip.split("%", 1)[0]).is_loopback
    except ValueError:
        return ip in _LOOPBACKS


def _flow_ip(ip: str) -> str:
    try:
        return str(ipaddress.ip_address(ip.split("%", 1)[0]))
    except ValueError:
        return ip


def load_flow_owners() -> tuple[dict[tuple[str, int], int], dict[tuple[str, int], int]]:
    """Read TCP and UDP owner tables. Empty on non-Windows."""
    if os.name != "nt":
        return {}, {}
    tcp = {}
    tcp.update(_read_tcp4_owners())
    tcp.update(_read_tcp6_owners())
    udp = {}
    udp.update(_read_udp4_owners())
    udp.update(_read_udp6_owners())
    return tcp, udp


def _iphlpapi():
    import ctypes

    lib = ctypes.WinDLL("iphlpapi")
    dword = ctypes.c_ulong
    lib.GetExtendedTcpTable.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(dword),
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    lib.GetExtendedTcpTable.restype = ctypes.c_ulong
    lib.GetExtendedUdpTable.argtypes = lib.GetExtendedTcpTable.argtypes
    lib.GetExtendedUdpTable.restype = ctypes.c_ulong
    return lib


def _extended_table(udp: bool, family: int, table_class: int) -> bytes:
    import ctypes

    lib = _iphlpapi()
    fn = lib.GetExtendedUdpTable if udp else lib.GetExtendedTcpTable
    size = ctypes.c_ulong(0)
    fn(None, ctypes.byref(size), 0, family, table_class, 0)
    if size.value <= 0:
        return b""
    buf = ctypes.create_string_buffer(size.value)
    size = ctypes.c_ulong(len(buf))
    if fn(buf, ctypes.byref(size), 0, family, table_class, 0) != 0:
        return b""
    return buf.raw[: size.value]


def _port(value: int) -> int:
    return socket.ntohs(value & 0xFFFF)


def _read_tcp4_owners() -> dict[tuple[str, int], int]:
    import struct

    raw = _extended_table(False, 2, 5)
    if len(raw) < 4:
        return {}
    count = struct.unpack_from("<I", raw, 0)[0]
    row = 24
    found: dict[tuple[str, int], int] = {}
    for index in range(count):
        start = 4 + index * row
        if start + row > len(raw):
            break
        state, local, local_port, _remote, _remote_port, pid = struct.unpack_from("<IIIIII", raw, start)
        if state == 0 or pid <= 0:
            continue
        found[(socket.inet_ntoa(struct.pack("<I", local)), _port(local_port))] = pid
    return found


def _read_tcp6_owners() -> dict[tuple[str, int], int]:
    import struct

    raw = _extended_table(False, 23, 5)
    if len(raw) < 4:
        return {}
    count = struct.unpack_from("<I", raw, 0)[0]
    row = 56
    found: dict[tuple[str, int], int] = {}
    for index in range(count):
        start = 4 + index * row
        if start + row > len(raw):
            break
        local = raw[start : start + 16]
        local_port = struct.unpack_from("<I", raw, start + 20)[0]
        state = struct.unpack_from("<I", raw, start + 48)[0]
        pid = struct.unpack_from("<I", raw, start + 52)[0]
        if state == 0 or pid <= 0:
            continue
        found[(socket.inet_ntop(socket.AF_INET6, local), _port(local_port))] = pid
    return found


def _read_udp4_owners() -> dict[tuple[str, int], int]:
    import struct

    raw = _extended_table(True, 2, 1)
    if len(raw) < 4:
        return {}
    count = struct.unpack_from("<I", raw, 0)[0]
    row = 12
    found: dict[tuple[str, int], int] = {}
    for index in range(count):
        start = 4 + index * row
        if start + row > len(raw):
            break
        local, local_port, pid = struct.unpack_from("<III", raw, start)
        if pid <= 0:
            continue
        found[(socket.inet_ntoa(struct.pack("<I", local)), _port(local_port))] = pid
    return found


def _read_udp6_owners() -> dict[tuple[str, int], int]:
    import struct

    raw = _extended_table(True, 23, 1)
    if len(raw) < 4:
        return {}
    count = struct.unpack_from("<I", raw, 0)[0]
    row = 28
    found: dict[tuple[str, int], int] = {}
    for index in range(count):
        start = 4 + index * row
        if start + row > len(raw):
            break
        local = raw[start : start + 16]
        local_port = struct.unpack_from("<I", raw, start + 20)[0]
        pid = struct.unpack_from("<I", raw, start + 24)[0]
        if pid <= 0:
            continue
        found[(socket.inet_ntop(socket.AF_INET6, local), _port(local_port))] = pid
    return found


class NatTable:
    """Map an application socket to the destination it originally dialed.

    Entries expire after NAT_IDLE_SECONDS without packets, and immediately
    when the flow sends FIN or RST. The source-port-only fallback is only for
    loopback accept(), which can report 127.0.0.1 instead of the real client.
    """

    def __init__(self, clock=None) -> None:
        self._clock = clock or time.monotonic
        self._by_client: dict[tuple[str, int], tuple[str, int, float]] = {}
        self._by_port: dict[int, tuple[str, int, float]] = {}
        self._ifaces: dict[tuple[str, int], tuple[int, int]] = {}
        self._lock = threading.Lock()

    def remember(
        self,
        src: str,
        sport: int,
        dst: str,
        dport: int,
        iface: tuple[int, int] | None = None,
    ) -> None:
        now = self._clock()
        with self._lock:
            self._expire(now)
            self._by_client[(src, sport)] = (dst, dport, now)
            self._by_port[sport] = (dst, dport, now)
            if iface is not None:
                self._ifaces[(src, sport)] = iface

    def original(self, src: str, sport: int, *, peer_is_loopback: bool = False) -> tuple[str, int] | None:
        now = self._clock()
        with self._lock:
            self._expire(now)
            found = self._by_client.get((src, sport))
            client_key: tuple[str, int] | None = (src, sport) if found is not None else None
            if found is None and peer_is_loopback:
                found = self._by_port.get(sport)
            if found is None:
                return None
            dst, dport, _ts = found
            self._by_port[sport] = (dst, dport, now)
            if client_key is not None:
                self._by_client[client_key] = (dst, dport, now)
            else:
                for key, item in self._by_client.items():
                    if key[1] == sport and item[0] == dst and item[1] == dport:
                        self._by_client[key] = (dst, dport, now)
                        break
            return dst, dport

    def iface_for(self, src: str, sport: int) -> tuple[int, int] | None:
        with self._lock:
            return self._ifaces.get((src, sport))

    def forget(self, src: str, sport: int) -> None:
        with self._lock:
            found = self._by_client.get((src, sport))
            self._drop(src, sport, found)

    def _drop(self, src: str, sport: int, found: tuple[str, int, float] | None) -> None:
        self._by_client.pop((src, sport), None)
        self._ifaces.pop((src, sport), None)
        port_item = self._by_port.get(sport)
        if found is not None and port_item is not None and port_item[0] == found[0] and port_item[1] == found[1]:
            self._by_port.pop(sport, None)

    def _expire(self, now: float) -> None:
        stale = [key for key, item in self._by_client.items() if now - item[2] > NAT_IDLE_SECONDS]
        for src, sport in stale:
            self._drop(src, sport, self._by_client.get((src, sport)))


@dataclass(frozen=True)
class Rewrite:
    dst_addr: str | None = None
    dst_port: int | None = None
    src_addr: str | None = None
    src_port: int | None = None
    inbound: bool = False
    to_client: bool = False
    interface: tuple[int, int] | None = None


def decide(
    *,
    outbound: bool,
    src: str,
    sport: int,
    dst: str,
    dport: int,
    proto: str,
    ipv6_mode: str,
    local_v4: int,
    local_v6: int,
    nat: NatTable,
    fin: bool = False,
    rst: bool = False,
    iface: tuple[int, int] | None = None,
) -> Rewrite | str:
    """Return a Rewrite, 'reject', or 'pass'."""
    if outbound and _is_loopback_addr(src) and sport in (local_v4, local_v6) and sport > 0:
        orig = nat.original(dst, dport, peer_is_loopback=True)
        if orig is None:
            return "pass"
        if fin or rst:
            nat.forget(dst, dport)
        return Rewrite(src_addr=orig[0], src_port=orig[1], to_client=True)
    if not outbound:
        loopback = src in _LOOPBACKS
        orig = nat.original(dst, dport, peer_is_loopback=loopback)
        if orig is None:
            return "pass"
        if fin or rst:
            nat.forget(dst, dport)
        return Rewrite(src_addr=orig[0], src_port=orig[1], to_client=True)

    if is_direct_ip(dst):
        return "pass"
    if proto == "udp":
        return "reject" if dport == 443 else "pass"
    if proto != "tcp":
        return "pass"
    try:
        version = ipaddress.ip_address(dst).version
    except ValueError:
        return "pass"
    mode = normalize_ipv6_mode(ipv6_mode)
    if version == 6 and mode != "proxy":
        return "reject"
    local_port = local_v6 if version == 6 else local_v4
    if local_port <= 0:
        return "reject"
    nat.remember(src, sport, dst, dport, iface=iface)
    if fin or rst:
        nat.forget(src, sport)
    loopback = "::1" if version == 6 else "127.0.0.1"
    return Rewrite(dst_addr=loopback, dst_port=local_port, inbound=True)


def plan_packet(
    *,
    outbound: bool,
    src: str,
    sport: int,
    dst: str,
    dport: int,
    local_port: int,
    nat: NatTable,
) -> Rewrite | None:
    """IPv4 TCP helper kept for existing callers. None means send unchanged."""
    result = decide(
        outbound=outbound,
        src=src,
        sport=sport,
        dst=dst,
        dport=dport,
        proto="tcp",
        ipv6_mode="proxy",
        local_v4=local_port,
        local_v6=local_port,
        nat=nat,
    )
    return result if isinstance(result, Rewrite) else None


def injection_targets(
    rows: list[tuple[int, int, str]],
    wanted_exes: set[str],
    self_pid: int = 0,
    already: set[int] | None = None,
) -> set[int]:
    """Whitelist PIDs that still need the connect hook. Unlisted PIDs are absent."""
    done = already or set()
    return {pid for pid in select_pids(rows, wanted_exes, self_pid) if pid not in done}


def select_pids(
    rows: list[tuple[int, int, str]],
    wanted_exes: set[str],
    self_pid: int = 0,
) -> set[int]:
    """PIDs whose own name or an ancestor's name is in the whitelist."""
    wanted = {name.lower() for name in wanted_exes if name}
    by_pid = {int(pid): (int(ppid), (name or "").lower()) for pid, ppid, name in rows}
    found: set[int] = set()
    for pid in by_pid:
        if pid <= 0 or pid == self_pid:
            continue
        if _ancestor_wanted(pid, by_pid, wanted):
            found.add(pid)
    return found


def _ancestor_wanted(
    pid: int,
    by_pid: dict[int, tuple[int, str]],
    wanted: set[str],
) -> bool:
    seen: set[int] = set()
    current = pid
    for _ in range(_ANCESTOR_LIMIT):
        if current in seen or current not in by_pid:
            return False
        seen.add(current)
        parent, name = by_pid[current]
        if name in wanted:
            return True
        if parent <= 0 or parent == current:
            return False
        current = parent
    return False


def socks5_greeting() -> bytes:
    return b"\x05\x01\x00"


def socks5_connect_request(ip: str, port: int) -> bytes:
    addr = ipaddress.ip_address(ip)
    family = 1 if addr.version == 4 else 4
    return b"\x05\x01\x00" + bytes((family,)) + addr.packed + int(port).to_bytes(2, "big")


def _recvn(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def socks5_connect(sock: socket.socket, ip: str, port: int) -> socket.socket:
    """Complete a SOCKS5 CONNECT on an already-connected socket. Returns it."""
    sock.sendall(socks5_greeting())
    hello = _recvn(sock, 2)
    if hello != b"\x05\x00":
        raise OSError(f"SOCKS5 rejected authentication: {hello!r}")
    sock.sendall(socks5_connect_request(ip, port))
    hdr = _recvn(sock, 4)
    if len(hdr) < 4 or hdr[0] != 5 or hdr[1] != 0:
        raise OSError(f"SOCKS5 connect failed: {hdr!r}")
    atyp = hdr[3]
    if atyp == 1:
        _recvn(sock, 6)
    elif atyp == 4:
        _recvn(sock, 18)
    elif atyp == 3:
        ln = _recvn(sock, 1)
        if ln:
            _recvn(sock, ln[0] + 2)
    return sock


def _pump(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock, how in ((src, socket.SHUT_RD), (dst, socket.SHUT_WR)):
            try:
                sock.shutdown(how)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


def _relay(left: socket.socket, right: socket.socket) -> None:
    left.settimeout(RELAY_IDLE_SECONDS)
    right.settimeout(RELAY_IDLE_SECONDS)
    threading.Thread(target=_pump, args=(left, right), daemon=True).start()
    threading.Thread(target=_pump, args=(right, left), daemon=True).start()


def _apply_rewrite(packet, rewrite: Rewrite) -> None:
    if rewrite.dst_addr is not None:
        packet.dst_addr = rewrite.dst_addr
    if rewrite.dst_port is not None:
        packet.dst_port = rewrite.dst_port
    if rewrite.src_addr is not None:
        packet.src_addr = rewrite.src_addr
    if rewrite.src_port is not None:
        packet.src_port = rewrite.src_port
    if rewrite.inbound or rewrite.to_client:
        import pydivert

        packet.direction = pydivert.Direction.INBOUND
        # The SYN must arrive on the loopback interface or 127.0.0.1 never
        # accepts it. The SYN-ACK must arrive on the interface the application
        # socket is waiting on, which is the one that sent the original SYN.
        packet.is_loopback = bool(rewrite.inbound)
        if rewrite.inbound:
            packet.interface = (1, 0)
        elif rewrite.interface is not None:
            packet.interface = rewrite.interface


def _send_tcp_reset(divert, packet) -> None:
    """Turn a captured outbound TCP packet into an inbound RST and send it."""
    tcp = getattr(packet, "tcp", None)
    if tcp is None:
        return
    payload = packet.payload or b""
    extra = int(bool(tcp.syn)) + int(bool(tcp.fin))
    ack = (int(tcp.seq_num) + len(payload) + extra) & 0xFFFFFFFF
    packet.src_addr, packet.dst_addr = packet.dst_addr, packet.src_addr
    packet.src_port, packet.dst_port = packet.dst_port, packet.src_port
    tcp.seq_num = 0
    tcp.ack_num = ack
    tcp.syn = False
    tcp.ack = True
    tcp.rst = True
    tcp.psh = False
    tcp.fin = False
    packet.payload = b""
    import pydivert

    packet.direction = pydivert.Direction.INBOUND
    divert.send(packet)


class _Capture:
    def __init__(self) -> None:
        self.stop = threading.Event()
        self.divert = None


class BackendSupervisor:
    """Watch TUN. Run the per-app redirector only while TUN is down."""

    def __init__(self) -> None:
        self.status = "分应用转发未启动"
        self._exes: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._capture: _Capture | None = None
        self._slots = threading.Semaphore(HANDSHAKE_LIMIT)
        self._pids: set[int] = set()
        self._injected: set[int] = set()
        self._filter_lock = threading.Lock()
        self._packet_key: tuple | None = None
        self._listeners: list[socket.socket] = []
        self._listener_stop = threading.Event()
        self._connect_route: tuple[str, int] | None = None
        self._connect_mode = "reject"
        self._hook_map = None
        self._hook_view = None

    def set_exes(self, names: list[str]) -> None:
        with self._lock:
            self._exes = {n.strip().lower() for n in names if n.strip()}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="app-redirector", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._idle()

    def _idle(self) -> None:
        self._close_capture(self._capture)
        self._capture = None
        self._close_listeners()
        self._pids = set()
        self._injected.clear()

    def _loop(self) -> None:
        ticks = 0
        while not self._stop.wait(_PID_REFRESH_SECONDS):
            try:
                ticks += 1
                with self._lock:
                    exes = set(self._exes)
                if ticks % _TUN_CHECK_EVERY == 1 and self._tun_up():
                    self._idle()
                    self.status = "后端: TUN（本机转发已停）"
                    continue
                if not exes:
                    self._idle()
                    self.status = "后端: 直连（未勾选应用）"
                    continue
                host, port = _proxy_endpoint()
                mode = _ipv6_mode()
                err = self._ensure_connect(host, port, mode)
                if err:
                    self.status = err
                    continue
                rows = self._refresh_pids(exes)
                self._inject_hooks(exes, rows)
                udp_err = self._ensure_packet_filter()
                label = "IPv6 代理" if mode == "proxy" else "IPv6 拒绝"
                if not self._pids:
                    self.status = f"后端: 等待白名单进程启动（{label}）"
                else:
                    self.status = (
                        f"后端: 已挂钩 {len(self._injected)}/{len(self._pids)} 个进程 → {host}:{port}（{label}）"
                    )
                if udp_err:
                    self.status = f"{self.status}；{udp_err}"
            except Exception as ex:  # noqa: BLE001
                self.status = f"后端异常: {ex}"

    def _refresh_pids(self, exes: set[str]) -> list[tuple[int, int, str]]:
        rows = _process_rows()
        alive = {pid for pid, _ppid, _name in rows}
        allowed = select_pids(rows, exes, os.getpid())
        self._injected &= alive
        with self._filter_lock:
            if allowed != self._pids:
                self._pids = allowed
        return rows

    def _inject_hooks(self, exes: set[str], rows: list[tuple[int, int, str]]) -> None:
        try:
            dll = str(ensure_hook_dll())
        except (OSError, RuntimeError) as ex:
            self.status = f"后端: 连接钩子未就绪 ({ex})"
            return
        targets = injection_targets(rows, exes, os.getpid(), self._injected)
        for pid in sorted(targets):
            try:
                inject_hook_dll(pid, dll)
            except OSError:
                continue
            self._injected.add(pid)

    def _tun_up(self) -> bool:
        # Only an Up adapter counts. A leftover Clash service with no TUN NIC
        # must not disable per-app forwarding.
        try:
            from tun_overlay import _up_adapter_names
        except ImportError:
            return False
        return any(looks_like_tun(name) for name in _up_adapter_names())

    def _ensure_connect(self, host: str, port: int, mode: str) -> str | None:
        self._connect_route = (host, port)
        self._connect_mode = mode
        try:
            if not self._listeners:
                self._listener_stop.clear()
                v4 = _bind_listener("127.0.0.1")
                self._listeners.append(v4)
                threading.Thread(
                    target=self._accept_loop, args=(v4,), name="redirect-accept", daemon=True
                ).start()
            # AF_INET6 sockets, including IPv4-mapped addresses, connect to ::1.
            if len(self._listeners) == 1:
                v6 = _bind_listener("::1")
                self._listeners.append(v6)
                threading.Thread(
                    target=self._accept_loop, args=(v6,), name="redirect-accept6", daemon=True
                ).start()
            self._publish_hook_config(mode)
        except OSError as ex:
            self._close_listeners()
            return f"后端: 本机连接端口失败 ({ex})"
        return None

    def _publish_hook_config(self, mode: str) -> None:
        import ctypes
        from ctypes import wintypes

        class HookConfig(ctypes.Structure):
            _pack_ = 1
            _fields_ = [
                ("magic", ctypes.c_char * 4),
                ("v4_port", ctypes.c_uint16),
                ("v6_port", ctypes.c_uint16),
                ("ipv6_proxy", ctypes.c_uint8),
                ("pad", ctypes.c_uint8),
            ]

        if self._hook_view is None:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateFileMappingW.argtypes = [
                wintypes.HANDLE,
                ctypes.c_void_p,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.LPCWSTR,
            ]
            kernel.CreateFileMappingW.restype = wintypes.HANDLE
            kernel.MapViewOfFile.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_size_t,
            ]
            kernel.MapViewOfFile.restype = ctypes.c_void_p
            mapping = kernel.CreateFileMappingW(
                wintypes.HANDLE(-1).value,
                None,
                0x04,
                0,
                ctypes.sizeof(HookConfig),
                "Local\\MaintainAllAppProxyHook",
            )
            if not mapping:
                raise OSError("hook config mapping failed")
            view = kernel.MapViewOfFile(mapping, 0x0002, 0, 0, ctypes.sizeof(HookConfig))
            if not view:
                kernel.CloseHandle(mapping)
                raise OSError("hook config view failed")
            self._hook_map = mapping
            self._hook_view = view
        cfg = HookConfig.from_address(self._hook_view)
        cfg.magic = b"MAC1"
        cfg.v4_port = int(self._listeners[0].getsockname()[1]) if self._listeners else 0
        cfg.v6_port = int(self._listeners[1].getsockname()[1]) if len(self._listeners) > 1 else 0
        cfg.ipv6_proxy = 1 if mode == "proxy" else 0
        cfg.pad = 0

    def _close_listeners(self) -> None:
        self._listener_stop.set()
        self._clear_hook_config()
        for listen in list(self._listeners):
            try:
                listen.close()
            except OSError:
                pass
        self._listeners = []
        self._listener_stop = threading.Event()
        self._connect_route = None

    def _clear_hook_config(self) -> None:
        import ctypes

        view = self._hook_view
        mapping = self._hook_map
        self._hook_view = None
        self._hook_map = None
        if view:
            ctypes.memset(view, 0, 4)
            ctypes.windll.kernel32.UnmapViewOfFile(view)
        if mapping:
            ctypes.windll.kernel32.CloseHandle(mapping)

    def _ensure_packet_filter(self) -> str | None:
        with self._filter_lock:
            pids = set(self._pids)
            key = (tuple(sorted(pids)),)
            if not pids:
                self._close_capture(self._capture)
                self._capture = None
                return None
            if key == self._packet_key and self._capture is not None:
                return None
            err = self._swap_capture(pids)
            if err is None:
                self._packet_key = key
            return err

    def _swap_capture(self, pids: set[int]) -> str | None:
        """Open the new UDP filter before closing the previous one. TCP is not captured."""
        try:
            import pydivert
        except ImportError:
            return "UDP 443 未拦截（未安装 pydivert）"
        filt = build_filter(pids)
        if filt is None:
            return None
        try:
            divert = pydivert.WinDivert(filt)
            divert.open()
        except OSError as ex:
            return f"UDP 443 未拦截 ({ex})"
        fresh = _Capture()
        fresh.divert = divert
        previous = self._capture
        self._capture = fresh
        threading.Thread(
            target=self._packet_loop, args=(fresh, fresh.divert), name="redirect-udp", daemon=True
        ).start()
        self._close_capture(previous)
        return None

    def _close_capture(self, capture: _Capture | None) -> None:
        if capture is None:
            return
        capture.stop.set()
        self._packet_key = None
        divert = capture.divert
        capture.divert = None
        if divert is not None:
            try:
                divert.close()
            except OSError:
                pass

    def _packet_loop(self, capture: _Capture, divert) -> None:
        while divert is not None and not capture.stop.is_set():
            try:
                packet = divert.recv()
            except OSError:
                break
            try:
                udp = getattr(packet, "udp", None)
                if udp is not None and int(packet.dst_port or 0) == 443:
                    continue
                divert.send(packet)
            except OSError:
                try:
                    divert.send(packet)
                except OSError:
                    break

    def _accept_loop(self, listen: socket.socket) -> None:
        while not self._listener_stop.is_set():
            try:
                client, _addr = listen.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()

    def _handle_client(self, client: socket.socket) -> None:
        route = self._connect_route
        if route is None:
            client.close()
            return
        if not self._slots.acquire(blocking=False):
            client.close()
            return
        try:
            remote = open_redirected_upstream(client, route[0], route[1], self._connect_mode)
        finally:
            self._slots.release()
        if remote is not None:
            _relay(client, remote)


def ensure_hook_dll() -> Path:
    """Build connect_hook.dll when the source is newer. Raises if clang is missing."""
    src = Path(__file__).with_name("connect_hook.c")
    dll = Path(__file__).with_name("connect_hook.dll")
    if dll.is_file() and dll.stat().st_mtime >= src.stat().st_mtime:
        return dll
    clang = shutil.which("clang")
    if not clang:
        raise RuntimeError("clang was not found")
    subprocess.run(
        [clang, "-shared", "-O2", "-Wall", "-o", str(dll), str(src), "-lws2_32"],
        check=True,
        cwd=str(src.parent),
    )
    return dll


def inject_hook_dll(pid: int, dll_path: str) -> None:
    """Load the connect hook into one process and call HookInstall. Other PIDs are untouched."""
    import ctypes
    from ctypes import wintypes

    if pid <= 0:
        raise OSError("invalid pid")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.IsWow64Process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    kernel.IsWow64Process.restype = wintypes.BOOL
    kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel.GetModuleHandleW.restype = wintypes.HMODULE
    kernel.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
    kernel.GetProcAddress.restype = ctypes.c_void_p
    kernel.VirtualFreeEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
    kernel.VirtualFreeEx.restype = wintypes.BOOL
    process = kernel.OpenProcess(0x043A, False, pid)
    if not process:
        raise OSError(ctypes.get_last_error(), f"OpenProcess {pid}")
    remote_path = 0
    try:
        wow = wintypes.BOOL()
        if kernel.IsWow64Process(process, ctypes.byref(wow)) and wow.value:
            raise OSError(f"32-bit pid {pid} is not hooked")
        remote_path = _remote_wstring(kernel, process, dll_path)
        if _remote_thread_exit(kernel, process, _load_library_addr(kernel), remote_path) == 0:
            raise OSError(f"LoadLibrary failed in pid {pid}")
        base = _remote_module_base(pid)
        local = ctypes.WinDLL(dll_path)
        local_base = int(local._handle)
        hook = kernel.GetProcAddress(local._handle, b"HookInstall")
        if not base or not hook:
            raise OSError(f"HookInstall missing for pid {pid}")
        _remote_thread_exit(kernel, process, base + (int(hook) - local_base), None)
    finally:
        if remote_path:
            kernel.VirtualFreeEx(process, remote_path, 0, 0x8000)
        kernel.CloseHandle(process)


def _load_library_addr(kernel) -> int:
    module = kernel.GetModuleHandleW("kernel32.dll")
    addr = kernel.GetProcAddress(module, b"LoadLibraryW")
    if not addr:
        raise OSError("LoadLibraryW was not found")
    return int(addr)


def _remote_wstring(kernel, process, text: str) -> int:
    import ctypes
    from ctypes import wintypes

    raw = (text + "\0").encode("utf-16le")
    kernel.VirtualAllocEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_size_t,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    kernel.VirtualAllocEx.restype = ctypes.c_void_p
    kernel.WriteProcessMemory.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
    ]
    kernel.WriteProcessMemory.restype = wintypes.BOOL
    remote = kernel.VirtualAllocEx(process, None, len(raw), 0x3000, 0x04)
    if not remote:
        raise OSError("VirtualAllocEx failed")
    buf = ctypes.create_string_buffer(raw)
    if not kernel.WriteProcessMemory(process, remote, buf, len(raw), None):
        raise OSError("WriteProcessMemory failed")
    return int(remote)


def _remote_thread_exit(kernel, process, start: int, arg: int | None) -> int:
    import ctypes
    from ctypes import wintypes

    kernel.CreateRemoteThread.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    kernel.CreateRemoteThread.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeThread.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeThread.restype = wintypes.BOOL
    thread = kernel.CreateRemoteThread(process, None, 0, start, arg, 0, None)
    if not thread:
        raise OSError(ctypes.get_last_error(), "CreateRemoteThread")
    try:
        kernel.WaitForSingleObject(thread, 10000)
        code = wintypes.DWORD()
        kernel.GetExitCodeThread(thread, ctypes.byref(code))
        return int(code.value)
    finally:
        kernel.CloseHandle(thread)


def _remote_module_base(pid: int) -> int:
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class MODULEENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("th32ModuleID", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("GlblcntUsage", wintypes.DWORD),
            ("ProccntUsage", wintypes.DWORD),
            ("modBaseAddr", ctypes.c_void_p),
            ("modBaseSize", wintypes.DWORD),
            ("hModule", wintypes.HMODULE),
            ("szModule", wintypes.WCHAR * 256),
            ("szExePath", wintypes.WCHAR * 260),
        ]

    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
    kernel.Module32FirstW.restype = wintypes.BOOL
    kernel.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
    kernel.Module32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = kernel.CreateToolhelp32Snapshot(0x00000008, pid)
    invalid = ctypes.c_void_p(-1).value
    if not snap or snap == invalid:
        return 0
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(MODULEENTRY32W)
        if not kernel.Module32FirstW(snap, ctypes.byref(entry)):
            return 0
        while True:
            if entry.szModule.lower() == "connect_hook.dll":
                return int(entry.modBaseAddr or 0)
            if not kernel.Module32NextW(snap, ctypes.byref(entry)):
                return 0
    finally:
        kernel.CloseHandle(snap)


def _bind_listener(host: str) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    listen = socket.socket(family)
    if family == socket.AF_INET6:
        listen.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listen.bind((host, 0))
    listen.listen(LISTEN_BACKLOG)
    listen.settimeout(0.5)
    return listen


def _proxy_endpoint() -> tuple[str, int]:
    from install import load_state

    st = load_state()
    host = (st.proxy_host or "").strip()
    if not host or "<" in host:
        raise RuntimeError("proxy host is not configured")
    return host, int(st.socks_port)


def _ipv6_mode() -> str:
    from install import load_state

    return normalize_ipv6_mode(getattr(load_state(), "ipv6_mode", "reject"))


def _pids_for_exes(exes: set[str]) -> set[int]:
    if os.name != "nt":
        return set()
    return select_pids(_process_rows(), exes, self_pid=os.getpid())


def _process_rows() -> list[tuple[int, int, str]]:
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    kernel = ctypes.windll.kernel32

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    snap = kernel.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value:
        return []
    rows: list[tuple[int, int, str]] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel.Process32FirstW(snap, ctypes.byref(entry)):
            return []
        while True:
            rows.append((int(entry.th32ProcessID), int(entry.th32ParentProcessID), entry.szExeFile))
            if not kernel.Process32NextW(snap, ctypes.byref(entry)):
                break
    finally:
        kernel.CloseHandle(snap)
    return rows
