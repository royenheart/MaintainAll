from __future__ import annotations

import socket
import threading

from redirector import (
    NAT_IDLE_SECONDS,
    NatTable,
    FlowOwners,
    build_filter,
    decide,
    encode_connect_preamble,
    hook_action,
    injection_targets,
    is_direct_ip,
    looks_like_tun,
    open_redirected_upstream,
    plan_packet,
    plan_upstream,
    read_connect_preamble,
    select_pids,
    should_capture_process,
    socks5_connect_request,
    socks5_greeting,
)


def test_lan_and_loopback_stay_direct():
    assert is_direct_ip("127.0.0.1")
    assert is_direct_ip("192.168.1.20")
    assert is_direct_ip("10.1.2.3")
    assert is_direct_ip("100.64.1.1")
    assert not is_direct_ip("203.0.113.10")


def test_tun_names():
    assert looks_like_tun("Mihomo")
    assert looks_like_tun("Clash Tunnel")
    assert not looks_like_tun("WLAN 7")
    assert not looks_like_tun("Tailscale")


def test_filter_is_udp_443_for_listed_pids_only():
    filt = build_filter({10, 20}, 17890, local_v6=17891, ipv6_mode="proxy")
    assert filt == "outbound and udp.DstPort == 443 and (processId == 10 or processId == 20)"
    assert "processId == 0" not in filt
    assert "tcp" not in filt
    assert "17890" not in filt
    assert "17891" not in filt


def test_empty_pids_do_not_open_a_filter():
    assert build_filter(set(), 1) is None
    assert build_filter(set()) is None


def test_unlisted_process_is_not_injected_or_filtered():
    rows = [
        (10, 1, "explorer.exe"),
        (20, 10, "ChatGPT.exe"),
        (21, 20, "msedgewebview2.exe"),
        (50, 10, "Cursor.exe"),
        (51, 50, "Cursor.exe"),
    ]
    targets = injection_targets(rows, {"chatgpt.exe"}, self_pid=0, already=set())
    assert targets == {20, 21}
    assert 50 not in targets
    assert 51 not in targets
    filt = build_filter(targets)
    assert filt is not None
    assert "processId == 50" not in filt
    assert "processId == 51" not in filt
    assert "processId == 0" not in filt
    again = injection_targets(rows, {"chatgpt.exe"}, self_pid=20, already={21})
    assert 20 not in again
    assert 50 not in again
    assert again == set()


def test_unknown_pid_is_not_captured():
    assert should_capture_process(0, {10}) is False
    assert should_capture_process(11, {10}) is False
    assert should_capture_process(10, {10}) is True


def test_public_outbound_is_redirected_and_reply_is_rewritten():
    nat = NatTable()
    out = plan_packet(
        outbound=True,
        src="192.168.1.10",
        sport=40000,
        dst="203.0.113.10",
        dport=443,
        local_port=17890,
        nat=nat,
    )
    assert out is not None
    assert out.dst_addr == "127.0.0.1"
    assert out.dst_port == 17890
    assert out.inbound is True
    assert nat.original("192.168.1.10", 40000) == ("203.0.113.10", 443)

    back = plan_packet(
        outbound=False,
        src="127.0.0.1",
        sport=17890,
        dst="192.168.1.10",
        dport=40000,
        local_port=17890,
        nat=nat,
    )
    assert back is not None
    assert back.src_addr == "203.0.113.10"
    assert back.src_port == 443


def test_private_outbound_is_left_alone():
    nat = NatTable()
    assert (
        plan_packet(
            outbound=True,
            src="192.168.1.10",
            sport=1,
            dst="192.168.1.20",
            dport=20170,
            local_port=17890,
            nat=nat,
        )
        is None
    )


def test_socks5_connect_bytes():
    assert socks5_greeting() == b"\x05\x01\x00"
    req = socks5_connect_request("203.0.113.10", 443)
    assert req[:4] == b"\x05\x01\x00\x01"
    assert req[4:8] == socket.inet_aton("203.0.113.10")
    assert int.from_bytes(req[8:10], "big") == 443
    v6 = socks5_connect_request("2001:db8::1", 443)
    assert v6[:4] == b"\x05\x01\x00\x04"
    assert v6[4:20] == socket.inet_pton(socket.AF_INET6, "2001:db8::1")


def test_ipv6_loopback_stays_direct_and_global_is_not():
    assert is_direct_ip("::1")
    assert is_direct_ip("fe80::1")
    assert is_direct_ip("fd00::1")
    assert not is_direct_ip("2001:db8::1")


def test_ipv6_reject_and_proxy_and_udp_443():
    nat = NatTable()
    assert (
        decide(
            outbound=True,
            src="2001:db8::14",
            sport=9,
            dst="2001:db8::1",
            dport=443,
            proto="tcp",
            ipv6_mode="reject",
            local_v4=1,
            local_v6=2,
            nat=nat,
        )
        == "reject"
    )
    proxied = decide(
        outbound=True,
        src="2001:db8::14",
        sport=9,
        dst="2001:db8::1",
        dport=443,
        proto="tcp",
        ipv6_mode="proxy",
        local_v4=1,
        local_v6=2,
        nat=nat,
    )
    assert proxied is not None
    assert proxied.dst_addr == "::1"
    assert proxied.dst_port == 2
    assert (
        decide(
            outbound=True,
            src="192.168.1.10",
            sport=9,
            dst="203.0.113.10",
            dport=443,
            proto="udp",
            ipv6_mode="proxy",
            local_v4=1,
            local_v6=2,
            nat=nat,
        )
        == "reject"
    )
    assert (
        decide(
            outbound=True,
            src="192.168.1.10",
            sport=9,
            dst="8.8.8.8",
            dport=53,
            proto="udp",
            ipv6_mode="reject",
            local_v4=1,
            local_v6=0,
            nat=nat,
        )
        == "pass"
    )


def test_ipv4_connect_is_redirected_and_never_refused():
    samples = [
        ("8.8.8.8", "reject", "redirect"),
        ("8.8.8.8", "proxy", "redirect"),
        ("74.125.1.1", "reject", "redirect"),
        ("0.0.0.0", "proxy", "original"),
        ("10.1.2.3", "proxy", "original"),
        ("100.64.0.1", "proxy", "original"),
        ("100.128.0.1", "proxy", "redirect"),
        ("127.0.0.1", "proxy", "original"),
        ("169.254.1.1", "proxy", "original"),
        ("172.16.0.1", "proxy", "original"),
        ("172.32.0.1", "proxy", "redirect"),
        ("192.168.1.20", "proxy", "original"),
        ("224.0.0.1", "proxy", "original"),
        ("::1", "reject", "original"),
        ("fe80::1", "reject", "original"),
        ("fd00::1", "reject", "original"),
        ("ff02::1", "reject", "original"),
        ("2001:db8::1", "reject", "refuse"),
        ("2001:db8::1", "proxy", "redirect"),
        ("::ffff:8.8.8.8", "reject", "redirect"),
        ("::ffff:192.168.0.1", "reject", "original"),
    ]
    for ip, mode, expected in samples:
        assert hook_action(ip, mode) == expected, (ip, mode)
        upstream = plan_upstream(ip, mode)
        if expected == "redirect":
            assert upstream == "socks"
        elif expected == "refuse":
            assert upstream == "refuse"
        else:
            assert upstream == "direct"
    assert plan_upstream("1.1.1.1", "reject") == "socks"
    assert plan_upstream("1.1.1.1", "proxy") == "socks"


def test_preamble_roundtrip():
    encoded = encode_connect_preamble("203.0.113.10", 443)
    assert encoded[:4] == b"MAC1"
    assert encoded[4] == 4

    left, right = socket.socketpair() if hasattr(socket, "socketpair") else (None, None)
    if left is None:
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        client = socket.create_connection(srv.getsockname(), timeout=2)
        right, _ = srv.accept()
        left = client
        srv.close()
    left.sendall(encoded)
    assert read_connect_preamble(right) == ("203.0.113.10", 443)
    v6 = encode_connect_preamble("2001:db8::1", 443)
    assert v6[4] == 6
    assert len(v6) == 23
    left.sendall(v6)
    assert read_connect_preamble(right) == ("2001:db8::1", 443)
    mapped = encode_connect_preamble("::ffff:1.2.3.4", 443)
    assert mapped[4] == 4
    assert mapped[5:9] == socket.inet_aton("1.2.3.4")
    left.close()
    right.close()


def test_redirected_client_uses_socks_connect():
    from redirector import socks5_connect

    upstream = socket.socket()
    upstream.bind(("127.0.0.1", 0))
    upstream.listen(1)
    port = upstream.getsockname()[1]
    seen: dict[str, bytes] = {}

    def fake_socks():
        conn, _ = upstream.accept()
        with conn:
            assert conn.recv(3) == b"\x05\x01\x00"
            conn.sendall(b"\x05\x00")
            req = conn.recv(10)
            seen["req"] = req
            conn.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("1.2.3.4") + (443).to_bytes(2, "big"))
            seen["payload"] = conn.recv(5)
            conn.sendall(b"pong")

    threading.Thread(target=fake_socks, daemon=True).start()
    pair_srv = socket.socket()
    pair_srv.bind(("127.0.0.1", 0))
    pair_srv.listen(1)
    app = socket.create_connection(pair_srv.getsockname(), timeout=2)
    client, _ = pair_srv.accept()
    pair_srv.close()

    def serve():
        remote = open_redirected_upstream(client, "127.0.0.1", port, "reject")
        assert remote is not None
        from redirector import _relay

        _relay(client, remote)

    threading.Thread(target=serve, daemon=True).start()
    app.sendall(encode_connect_preamble("203.0.113.10", 443))
    app.sendall(b"hello")
    assert app.recv(4) == b"pong"
    for _ in range(50):
        if "payload" in seen:
            break
        threading.Event().wait(0.02)
    assert seen["req"][3] == 1
    assert seen["req"][4:8] == socket.inet_aton("203.0.113.10")
    assert seen["payload"] == b"hello"
    app.close()
    upstream.close()
    assert socks5_connect is not None


def test_hook_dll_matches_python_policy():
    import os

    if os.name != "nt":
        return
    from redirector import ensure_hook_dll

    try:
        dll_path = ensure_hook_dll()
    except (OSError, RuntimeError):
        return
    import ctypes

    dll = ctypes.WinDLL(str(dll_path))
    dll.hook_action_ip.argtypes = [ctypes.c_char_p, ctypes.c_int]
    dll.hook_action_ip.restype = ctypes.c_int
    dll.hook_encode_preamble.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
    dll.hook_encode_preamble.restype = ctypes.c_int
    dll.hook_prologue_ok.restype = ctypes.c_int
    names = {0: "original", 1: "redirect", 2: "refuse"}
    for ip, mode, expected in (
        ("8.8.8.8", 0, "redirect"),
        ("192.168.1.20", 1, "original"),
        ("100.64.1.1", 0, "original"),
        ("100.128.0.1", 0, "redirect"),
        ("172.31.1.1", 0, "original"),
        ("172.32.1.1", 0, "redirect"),
        ("2001:db8::1", 0, "refuse"),
        ("2001:db8::1", 1, "redirect"),
        ("fe80::1", 0, "original"),
        ("::ffff:8.8.8.8", 0, "redirect"),
        ("::ffff:10.0.0.1", 0, "original"),
    ):
        got = names[dll.hook_action_ip(ip.encode(), mode)]
        assert got == expected, (ip, mode, got)
        assert hook_action(ip, "proxy" if mode else "reject") == expected
        out = ctypes.create_string_buffer(32)
        n = dll.hook_encode_preamble(ip.encode(), 443, out, 32)
        assert n > 0
        assert out.raw[:n] == encode_connect_preamble(ip, 443)
    # connect, WSAConnect, send, WSASend, closesocket, CreateProcessW/A, ConnectEx
    assert dll.hook_prologue_ok() == 0xFF


def test_flow_owner_lookup_does_not_read_the_os():
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return ({("192.168.1.10", 40000): 35848}, {})

    owners = FlowOwners(loader=loader)
    assert owners.lookup("192.168.1.10", 40000, "tcp") == 0
    assert calls["n"] == 0
    owners.refresh()
    assert owners.lookup("192.168.1.10", 40000, "tcp") == 35848
    assert owners.lookup("10.0.0.1", 1, "tcp") == 0
    assert calls["n"] == 1


def test_nat_expires_and_port_fallback_is_loopback_only():
    now = [0.0]
    nat = NatTable(clock=lambda: now[0])
    nat.remember("192.168.1.10", 40000, "203.0.113.10", 443)
    nat.remember("10.1.1.1", 40000, "1.1.1.1", 443)
    assert nat.original("10.0.0.9", 40000) is None
    assert nat.original("127.0.0.1", 40000, peer_is_loopback=True) == ("1.1.1.1", 443)
    now[0] = NAT_IDLE_SECONDS + 1
    assert nat.original("10.1.1.1", 40000) is None


def test_ipv4_listener_reply_is_rewritten_to_the_original_server():
    nat = NatTable()
    opened = decide(
        outbound=True,
        src="192.168.1.10",
        sport=40000,
        dst="64.233.188.138",
        dport=443,
        proto="tcp",
        ipv6_mode="reject",
        local_v4=17890,
        local_v6=0,
        nat=nat,
    )
    assert opened.dst_addr == "127.0.0.1"
    reply = decide(
        outbound=True,
        src="127.0.0.1",
        sport=17890,
        dst="192.168.1.10",
        dport=40000,
        proto="tcp",
        ipv6_mode="reject",
        local_v4=17890,
        local_v6=0,
        nat=nat,
    )
    assert reply.src_addr == "64.233.188.138"
    assert reply.src_port == 443
    assert reply.to_client is True


def test_fin_forgets_the_flow():
    nat = NatTable()
    decide(
        outbound=True,
        src="192.168.1.10",
        sport=40000,
        dst="203.0.113.10",
        dport=443,
        proto="tcp",
        ipv6_mode="proxy",
        local_v4=17890,
        local_v6=0,
        nat=nat,
        fin=True,
    )
    assert nat.original("192.168.1.10", 40000) is None


def test_descendant_of_whitelisted_process_is_included():
    rows = [
        (1, 0, "System"),
        (10, 1, "explorer.exe"),
        (20, 10, "ChatGPT.exe"),
        (21, 20, "msedgewebview2.exe"),
        (30, 10, "msedgewebview2.exe"),
        (40, 20, "ChatGPT.exe"),
    ]
    found = select_pids(rows, {"chatgpt.exe"}, self_pid=40)
    assert 20 in found
    assert 21 in found
    assert 30 not in found
    assert 40 not in found
    assert 10 not in found


def test_socks5_handshake_against_local_server():
    from redirector import socks5_connect

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def fake():
        conn, _ = srv.accept()
        with conn:
            greeting = conn.recv(3)
            assert greeting == b"\x05\x01\x00"
            conn.sendall(b"\x05\x00")
            req = conn.recv(10)
            assert req[3] == 1
            conn.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("1.2.3.4") + (443).to_bytes(2, "big"))
            conn.sendall(b"ok")

    threading.Thread(target=fake, daemon=True).start()
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    remote = socks5_connect(client, "203.0.113.10", 443)
    assert remote.recv(2) == b"ok"
    remote.close()
    srv.close()
