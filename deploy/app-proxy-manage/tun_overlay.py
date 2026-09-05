"""Keep Clash Verge TUN from hijacking DNS / LAN (Windows).

Verge's config.yaml defaults to `dns-hijack: [any:53]` and `stack: gvisor`.
That overlay wins over LMaintainAll.yaml and sends Chrome DNS into TUN.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROUTE_EXCLUDE_ADDRESSES = [
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.168.0.0/16",
    "224.0.0.0/4",
    "fc00::/7",
    "fe80::/10",
]

_SKIP_ADAPTER_RE = re.compile(
    r"tailscale|corplink|ivanti|pulse|wintun|mihomo|clash|"
    r"vethernet|vmware|npcap|loopback|bluetooth|isatap|teredo|hyper-v|wsl|"
    r"tap-windows|virtualbox|vpn",
    re.I,
)

_UNSET = object()
_iface_cache: str | None | object = _UNSET
_vpn_cache: list[str] | object = _UNSET


def reset_iface_cache() -> None:
    global _iface_cache, _vpn_cache
    _iface_cache = _UNSET
    _vpn_cache = _UNSET


def _ps(command: str) -> str:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.stdout or ""


def _up_adapter_names() -> list[str]:
    if os.name != "nt":
        return []
    out = _ps("Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object -ExpandProperty Name")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def vpn_interface_names() -> list[str]:
    global _vpn_cache
    if _vpn_cache is not _UNSET:
        return list(_vpn_cache)  # type: ignore[arg-type]
    names = [n for n in _up_adapter_names() if _SKIP_ADAPTER_RE.search(n)]
    _vpn_cache = names
    return list(names)


def detect_direct_interface() -> str | None:
    global _iface_cache
    if _iface_cache is not _UNSET:
        return _iface_cache  # type: ignore[return-value]
    if os.name != "nt":
        _iface_cache = None
        return None
    out = _ps(
        "Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' "
        "-ErrorAction SilentlyContinue | Sort-Object RouteMetric, InterfaceMetric | "
        "ForEach-Object { $_.InterfaceAlias }"
    )
    chosen = None
    for line in out.splitlines():
        name = line.strip()
        if name and not _SKIP_ADAPTER_RE.search(name):
            chosen = name
            break
    _iface_cache = chosen
    return chosen


def tun_dict(enable: bool, iface: str | None = None, vpn_ifaces: list[str] | None = None) -> dict:
    data = {
        "enable": bool(enable),
        "stack": "system",
        "auto-route": True,
        "strict-route": False,
        "dns-hijack": [],
        "route-exclude-address": list(ROUTE_EXCLUDE_ADDRESSES),
        "auto-detect-interface": not bool(iface),
    }
    skip = vpn_ifaces if vpn_ifaces is not None else vpn_interface_names()
    if skip:
        data["exclude-interface"] = skip
    return data


def apply_tun_to_mapping(data: dict, *, enable: bool | None = None) -> dict:
    """Rewrite tun (+ optional interface-name) in a Clash mapping. Returns data."""
    cur = data.get("tun") if isinstance(data.get("tun"), dict) else {}
    en = bool(cur.get("enable")) if enable is None else bool(enable)
    iface = detect_direct_interface()
    data["tun"] = tun_dict(en, iface)
    if iface:
        data["interface-name"] = iface
    return data


def profile_network_prelude(enable_tun: bool) -> str:
    import yaml

    iface = detect_direct_interface()
    payload: dict = {"tun": tun_dict(enable_tun, iface)}
    if iface:
        payload["interface-name"] = iface
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).rstrip()


def _header_of(text: str) -> str:
    if text.startswith("#"):
        return text.splitlines()[0] + "\n"
    return ""


def patch_yaml_tun(path: Path, *, enable: bool | None = None) -> None:
    import yaml

    if not path.is_file():
        return
    raw = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"不是 YAML 对象: {path}")
    apply_tun_to_mapping(loaded, enable=enable)
    body = yaml.safe_dump(loaded, allow_unicode=True, sort_keys=False)
    path.write_text(_header_of(raw) + body, encoding="utf-8")
