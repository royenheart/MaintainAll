"""Keep Clash Verge TUN from hijacking DNS / LAN (Windows).

Verge's config.yaml defaults to `dns-hijack: [any:53]`, `stack: gvisor`,
and `ipv6: true`. Those keys win over LMaintainAll.yaml. IPv6 makes TUN
install a default route that Chrome treats as a successful handshake.
`dns_config.yaml` defaults to fake-ip on port 53, which does the same if
DNS override is switched on.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import subprocess
from pathlib import Path

PROFILE_FILE = "LMaintainAll.yaml"

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
_vpn_cache: list[str] | object = _UNSET


def reset_iface_cache() -> None:
    global _vpn_cache
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


def tun_dict(
    enable: bool,
    vpn_ifaces: list[str] | None = None,
    extra_exclude: list[str] | None = None,
) -> dict:
    excludes = list(ROUTE_EXCLUDE_ADDRESSES)
    for cidr in extra_exclude or []:
        if cidr not in excludes:
            excludes.append(cidr)
    data = {
        "enable": bool(enable),
        "stack": "system",
        "auto-route": True,
        "strict-route": False,
        "dns-hijack": [],
        "route-exclude-address": excludes,
        # Follow the current default route. A pinned interface-name stays
        # pointed at a NIC that has gone down, and a snapshot taken while TUN
        # is up can select the virtual adapter itself.
        "auto-detect-interface": True,
    }
    skip = vpn_ifaces if vpn_ifaces is not None else vpn_interface_names()
    if skip:
        data["exclude-interface"] = skip
    return data


def _resolve_host(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None)
    return [item[4][0] for item in infos]


def exclude_cidrs_for_host(host: str, resolve=None) -> list[str]:
    """Return /32 or /128 excludes so TUN does not capture the proxy itself."""
    host = (host or "").strip()
    if not host or "<" in host:
        return []
    try:
        ips = [str(ipaddress.ip_address(host))]
    except ValueError:
        lookup = resolve if resolve is not None else _resolve_host
        try:
            ips = [str(item) for item in lookup(host)]
        except OSError:
            return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in ips:
        text = str(raw).split("%", 1)[0].strip()
        if not text:
            continue
        try:
            addr = ipaddress.ip_address(text)
        except ValueError:
            continue
        cidr = f"{addr}/128" if addr.version == 6 else f"{addr}/32"
        if cidr in seen:
            continue
        seen.add(cidr)
        out.append(cidr)
    return out


def apply_tun_to_mapping(
    data: dict,
    *,
    enable: bool | None = None,
    extra_exclude: list[str] | None = None,
) -> dict:
    """Rewrite tun in a Clash mapping and drop any pinned interface. Returns data."""
    cur = data.get("tun") if isinstance(data.get("tun"), dict) else {}
    en = bool(cur.get("enable")) if enable is None else bool(enable)
    data.pop("interface-name", None)
    data["tun"] = tun_dict(en, extra_exclude=extra_exclude)
    if en:
        # config.yaml's ipv6:true is what Verge merges into the running core,
        # ahead of the profile's ipv6:false. With it on, TUN installs ::/1 and
        # 8000::/1. Chrome's handshake to that route succeeds locally, so it
        # never falls back to IPv4, then the DIRECT IPv6 dial times out.
        data["ipv6"] = False
    return data


def profile_network_prelude(enable_tun: bool, extra_exclude: list[str] | None = None) -> str:
    import yaml

    payload: dict = {"tun": tun_dict(enable_tun, extra_exclude=extra_exclude)}
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False).rstrip()


def safe_dns_mapping() -> dict:
    """DNS that stays on localhost. Verge's own file listens on :53 with fake-ip."""
    return {
        "enable": True,
        "listen": "127.0.0.1:1053",
        "ipv6": False,
        "enhanced-mode": "redir-host",
        "use-system-hosts": True,
        "nameserver": ["system", "223.5.5.5"],
        "fallback": [],
        "proxy-server-nameserver": ["system", "223.5.5.5"],
    }


def _header_of(text: str) -> str:
    if text.startswith("#"):
        return text.splitlines()[0] + "\n"
    return ""


def patch_yaml_tun(
    path: Path,
    *,
    enable: bool | None = None,
    extra_exclude: list[str] | None = None,
) -> None:
    import yaml

    if not path.is_file():
        return
    raw = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"不是 YAML 对象: {path}")
    apply_tun_to_mapping(loaded, enable=enable, extra_exclude=extra_exclude)
    body = yaml.safe_dump(loaded, allow_unicode=True, sort_keys=False)
    path.write_text(_header_of(raw) + body, encoding="utf-8")


def _load_yaml(path: Path) -> dict:
    import yaml

    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"不是 YAML 对象: {path}")
    return loaded


def _dump_yaml(data: dict, header: str = "") -> str:
    import yaml

    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    return f"{header}{body}" if header else body


def _owned_profile(data: dict) -> bool:
    return any(
        isinstance(item, dict) and item.get("name") == "upstream-socks"
        for item in (data.get("proxies") or [])
    )


def _proxy_host(data: dict) -> str:
    proxies = [item for item in (data.get("proxies") or []) if isinstance(item, dict)]
    for item in proxies:
        if item.get("name") == "upstream-socks" and item.get("server"):
            return str(item["server"])
    for item in proxies:
        if item.get("server"):
            return str(item["server"])
    return ""


def reassert_config_dir(cfg_dir: Path) -> bool:
    """Put back tun, IPv6, DNS, and China-direct rules after Verge rewrites them.

    Returns True when a file changed.
    """
    from profile_rules import process_names_from_rules, replace_process_rules

    changed = False
    profile_path = cfg_dir / "profiles" / PROFILE_FILE
    host = ""
    profile_procs: list[str] | None = None
    if profile_path.is_file():
        profile = _load_yaml(profile_path)
        host = _proxy_host(profile)
        if _owned_profile(profile):
            profile_procs = process_names_from_rules(profile)
    extra = exclude_cidrs_for_host(host)

    enable: bool | None = None
    verge_path = cfg_dir / "verge.yaml"
    if verge_path.is_file():
        raw = verge_path.read_text(encoding="utf-8")
        verge = _load_yaml(verge_path)
        if "enable_tun_mode" in verge:
            enable = bool(verge["enable_tun_mode"])
        if verge.get("enable_dns_settings") is not False:
            verge["enable_dns_settings"] = False
            verge_path.write_text(_dump_yaml(verge, _header_of(raw)), encoding="utf-8")
            changed = True

    for path in (cfg_dir / "config.yaml", cfg_dir / "clash-verge.yaml", profile_path):
        if not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8")
        data = _load_yaml(path)
        if profile_procs is not None and _owned_profile(data) and "rules" in data:
            replace_process_rules(data, profile_procs)
        apply_tun_to_mapping(data, enable=enable, extra_exclude=extra)
        text = _dump_yaml(data, _header_of(raw))
        if text != raw:
            path.write_text(text, encoding="utf-8")
            changed = True

    dns_path = cfg_dir / "dns_config.yaml"
    dns_text = _dump_yaml({"dns": safe_dns_mapping()}, "# Clash Verge DNS Config\n")
    if not dns_path.is_file() or dns_path.read_text(encoding="utf-8") != dns_text:
        dns_path.write_text(dns_text, encoding="utf-8")
        changed = True
    return changed
