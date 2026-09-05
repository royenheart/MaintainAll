from __future__ import annotations

from tun_overlay import apply_tun_to_mapping, tun_dict


def test_tun_dict_never_hijacks_dns():
    d = tun_dict(True, iface=None, vpn_ifaces=["Tailscale"])
    assert d["dns-hijack"] == []
    assert d["stack"] == "system"
    assert d["enable"] is True
    assert "192.168.0.0/16" in d["route-exclude-address"]
    assert "100.64.0.0/10" in d["route-exclude-address"]
    assert d["exclude-interface"] == ["Tailscale"]
    assert d["auto-detect-interface"] is True


def test_apply_keeps_physical_iface_when_provided(monkeypatch):
    monkeypatch.setattr("tun_overlay.detect_direct_interface", lambda: "WLAN 7")
    monkeypatch.setattr("tun_overlay.vpn_interface_names", lambda: ["Tailscale"])
    data = {
        "tun": {"enable": True, "dns-hijack": ["any:53"], "stack": "gvisor"},
        "mixed-port": 7897,
    }
    apply_tun_to_mapping(data, enable=True)
    assert data["mixed-port"] == 7897
    assert data["tun"]["dns-hijack"] == []
    assert data["tun"]["stack"] == "system"
    assert data["tun"]["auto-detect-interface"] is False
    assert data["interface-name"] == "WLAN 7"


def test_apply_can_disable_tun(monkeypatch):
    monkeypatch.setattr("tun_overlay.detect_direct_interface", lambda: None)
    monkeypatch.setattr("tun_overlay.vpn_interface_names", lambda: [])
    data = {"tun": {"enable": True, "dns-hijack": ["any:53"]}}
    apply_tun_to_mapping(data, enable=False)
    assert data["tun"]["enable"] is False
    assert data["tun"]["dns-hijack"] == []
