from __future__ import annotations

from tun_overlay import (
    apply_tun_to_mapping,
    exclude_cidrs_for_host,
    reassert_config_dir,
    safe_dns_mapping,
    tun_dict,
)


def test_tun_dict_never_hijacks_dns():
    d = tun_dict(True, vpn_ifaces=["Tailscale"])
    assert d["dns-hijack"] == []
    assert d["stack"] == "system"
    assert d["enable"] is True
    assert "192.168.0.0/16" in d["route-exclude-address"]
    assert "100.64.0.0/10" in d["route-exclude-address"]
    assert d["exclude-interface"] == ["Tailscale"]
    assert d["auto-detect-interface"] is True


def test_apply_does_not_pin_interface(monkeypatch):
    monkeypatch.setattr("tun_overlay.vpn_interface_names", lambda: ["Tailscale"])
    data = {
        "tun": {"enable": True, "dns-hijack": ["any:53"], "stack": "gvisor"},
        "interface-name": "WLAN 7",
        "mixed-port": 7897,
    }
    apply_tun_to_mapping(data, enable=True)
    assert data["mixed-port"] == 7897
    assert data["tun"]["dns-hijack"] == []
    assert data["tun"]["stack"] == "system"
    assert data["tun"]["auto-detect-interface"] is True
    assert "interface-name" not in data


def test_enabling_tun_forces_ipv6_off(monkeypatch):
    """Verge config.yaml ipv6:true overrides the profile and installs a TUN
    IPv6 default route. Chrome then completes the handshake locally and never
    falls back to IPv4."""
    monkeypatch.setattr("tun_overlay.vpn_interface_names", lambda: [])
    data = {"ipv6": True, "tun": {"enable": True, "stack": "gvisor"}}
    apply_tun_to_mapping(data, enable=True)
    assert data["ipv6"] is False


def test_disabling_tun_leaves_ipv6_alone(monkeypatch):
    monkeypatch.setattr("tun_overlay.vpn_interface_names", lambda: [])
    data = {"ipv6": True, "tun": {"enable": True}}
    apply_tun_to_mapping(data, enable=False)
    assert data["ipv6"] is True


def test_apply_can_disable_tun(monkeypatch):
    monkeypatch.setattr("tun_overlay.vpn_interface_names", lambda: [])
    data = {"tun": {"enable": True, "dns-hijack": ["any:53"]}}
    apply_tun_to_mapping(data, enable=False)
    assert data["tun"]["enable"] is False
    assert data["tun"]["dns-hijack"] == []


def test_public_proxy_is_excluded_from_tun():
    assert exclude_cidrs_for_host("8.8.8.8") == ["8.8.8.8/32"]
    assert exclude_cidrs_for_host("2001:db8::2") == ["2001:db8::2/128"]
    assert exclude_cidrs_for_host(
        "proxy.example",
        resolve=lambda _host: ["1.2.3.4", "2001:db8::9"],
    ) == ["1.2.3.4/32", "2001:db8::9/128"]
    assert exclude_cidrs_for_host("missing.example", resolve=lambda _host: []) == []


def test_safe_dns_does_not_hijack_port_53():
    dns = safe_dns_mapping()
    assert dns["listen"] == "127.0.0.1:1053"
    assert dns["enhanced-mode"] == "redir-host"
    assert dns["ipv6"] is False
    assert "fake-ip-range" not in dns


def test_reassert_repairs_verge_overrides(monkeypatch, tmp_path):
    monkeypatch.setattr("tun_overlay.vpn_interface_names", lambda: ["Tailscale"])
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "LMaintainAll.yaml").write_text(
        """
proxies:
  - name: upstream-socks
    type: socks5
    server: 8.8.4.4
    port: 20170
rules:
  - MATCH,DIRECT
tun:
  enable: true
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config.yaml").write_text(
        "ipv6: true\ninterface-name: WLAN 7\ntun:\n  enable: true\n  dns-hijack:\n    - any:53\n",
        encoding="utf-8",
    )
    (tmp_path / "dns_config.yaml").write_text(
        "dns:\n  enable: true\n  listen: :53\n  enhanced-mode: fake-ip\n  fake-ip-range: 198.18.0.1/16\n",
        encoding="utf-8",
    )
    (tmp_path / "verge.yaml").write_text(
        "enable_tun_mode: true\nenable_dns_settings: true\n",
        encoding="utf-8",
    )
    assert reassert_config_dir(tmp_path) is True
    import yaml

    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["ipv6"] is False
    assert "interface-name" not in cfg
    assert cfg["tun"]["auto-detect-interface"] is True
    assert cfg["tun"]["dns-hijack"] == []
    assert "8.8.4.4/32" in cfg["tun"]["route-exclude-address"]
    dns = yaml.safe_load((tmp_path / "dns_config.yaml").read_text(encoding="utf-8"))
    assert dns["dns"]["listen"] == "127.0.0.1:1053"
    assert "fake-ip-range" not in dns["dns"]
    verge = yaml.safe_load((tmp_path / "verge.yaml").read_text(encoding="utf-8"))
    assert verge["enable_dns_settings"] is False
    profile = yaml.safe_load((profiles / "LMaintainAll.yaml").read_text(encoding="utf-8"))
    assert profile["rules"][0] == "GEOSITE,cn,DIRECT"
    assert profile["rules"][1] == "GEOIP,CN,DIRECT,no-resolve"
    assert profile["rules"][-1] == "MATCH,DIRECT"
