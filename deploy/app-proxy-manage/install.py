"""Windows 分应用代理向导（Clash Verge Rev）。

询问任意 SOCKS5/HTTP 代理的主机与端口，安装/更新 Verge 并写入本地 profile，
然后启动分应用托盘供勾选应用。进程白名单不在向导里选。

  python deploy/app-proxy-manage/install.py
  python deploy/app-proxy-manage/install.py --check
  python deploy/app-proxy-manage/install.py --no-tray
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import winreg
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MaintainAll" / "app-proxy"
STATE_PATH = STATE_DIR / "wizard.json"
VERGE_WINGET_ID = "ClashVergeRev.ClashVergeRev"
MIHOMO_WINGET_ID = "MetaCubeX.Mihomo"
PROFILE_UID = "LMaintainAll"
PROFILE_FILE = f"{PROFILE_UID}.yaml"
PROFILE_NAME = "MaintainAll 分应用白名单"
VERGE_DIR_NAME = "io.github.clash-verge-rev.clash-verge-rev"
TRAY_RUN_NAME = "MaintainAllAppProxy"


@dataclass
class WizardState:
    proxy_host: str = ""
    socks_port: int = 1080
    http_port: int = 8080
    outbound: str = "socks"  # socks | http
    processes: list[str] = field(default_factory=list)
    enable_tun: bool = False
    enable_auto_launch: bool = True
    upgrade_verge: bool = False


def _die(msg: str, code: int = 1) -> None:
    print(f"错误: {msg}", file=sys.stderr)
    raise SystemExit(code)


def ensure_deps(*, gui: bool = False) -> None:
    missing = False
    try:
        import questionary  # noqa: F401
        import yaml  # noqa: F401
    except ImportError:
        missing = True
    if gui:
        try:
            import PIL  # noqa: F401
            import pystray  # noqa: F401
        except ImportError:
            missing = True
    if not missing:
        return
    req = ROOT / "requirements.txt"
    print(f"安装依赖: {sys.executable} -m pip install -r {req}")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req)],
        check=False,
    )
    if r.returncode != 0:
        _die("无法安装依赖，请先手动 pip install -r deploy/app-proxy-manage/requirements.txt")


def load_state() -> WizardState:
    if not STATE_PATH.is_file():
        return WizardState()
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        filtered = {k: v for k, v in data.items() if k in WizardState.__dataclass_fields__}
        st = WizardState(**filtered)
        st.processes = [p.strip() for p in st.processes if str(p).strip()]
        return st
    except (OSError, json.JSONDecodeError, TypeError):
        return WizardState()


def save_state(st: WizardState) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(asdict(st), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verge_config_dir() -> Path:
    roaming = Path(os.environ.get("APPDATA", "")) / VERGE_DIR_NAME
    return roaming


def find_verge_exe() -> Path | None:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    candidates = [
        local / "Programs" / "Clash Verge" / "clash-verge.exe",
        pf / "Clash Verge" / "clash-verge.exe",
        pf / "Clash Verge Rev" / "clash-verge.exe",
    ]
    for p in candidates:
        if p.is_file():
            return p
    hit = shutil.which("clash-verge.exe")
    return Path(hit) if hit else None


_WINGET_NO_MATCH = (
    "找不到与输入条件匹配的已安装程序包",
    "No installed package found matching input criteria",
)


def _winget() -> str | None:
    return shutil.which("winget")


def _winget_run(args: list[str]) -> subprocess.CompletedProcess[str]:
    winget = _winget()
    if not winget:
        _die("未找到 winget。请先安装 Microsoft App Installer。")
    return subprocess.run(
        [winget, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _winget_output(r: subprocess.CompletedProcess[str]) -> str:
    return f"{r.stdout or ''}\n{r.stderr or ''}"


def winget_has(pkg_id: str) -> bool:
    if not _winget():
        return False
    r = _winget_run(["list", "--id", pkg_id, "-e", "--accept-source-agreements"])
    text = _winget_output(r)
    if r.returncode != 0:
        return False
    if any(m in text for m in _WINGET_NO_MATCH):
        return False
    for line in text.splitlines():
        if pkg_id in line and not line.strip().startswith("--id"):
            return True
    return False


def winget_install_or_upgrade(upgrade: bool) -> None:
    exe_present = find_verge_exe() is not None
    tracked = winget_has(VERGE_WINGET_ID)

    if exe_present and not tracked:
        if upgrade:
            print("本机已有 Clash Verge，但 winget 未登记该包，跳过升级。")
        else:
            print("本机已有 clash-verge.exe，跳过安装。")
        return

    if tracked and not upgrade:
        print(f"已安装 {VERGE_WINGET_ID}，跳过。")
        return

    if not _winget():
        if exe_present:
            print("没有 winget，沿用已有的 Clash Verge。")
            return
        _die("未找到 winget。请先安装 Microsoft App Installer。")

    cmd = "upgrade" if tracked else "install"
    print(f"winget {cmd} {VERGE_WINGET_ID} ...")
    extra = [
        "--id",
        VERGE_WINGET_ID,
        "-e",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    r = _winget_run([cmd, *extra] if cmd == "upgrade" else [cmd, *extra, "--scope", "user"])
    if r.returncode == 0:
        return
    if cmd == "install":
        print("用户范围失败，改试 machine（可能弹出 UAC）...")
        r = subprocess.run(
            [_winget(), cmd, *extra, "--scope", "machine"],
            check=False,
        )
        if r.returncode == 0:
            return
    if cmd == "upgrade" or find_verge_exe():
        print(f"winget {cmd} 未成功 (exit {r.returncode})，继续使用已安装的 Clash Verge。")
        print((_winget_output(r) if hasattr(r, "stdout") else "").strip()[:400])
        return
    _die(f"winget {cmd} 失败 (exit {r.returncode})")


def winget_uninstall(pkg_id: str) -> None:
    if not winget_has(pkg_id):
        print(f"未安装 {pkg_id}，跳过。")
        return
    winget = _winget()
    if not winget:
        print(f"没有 winget，请到「应用和功能」里手动卸载 {pkg_id}。")
        return
    print(f"winget uninstall {pkg_id} ...")
    r = subprocess.run(
        [
            winget,
            "uninstall",
            "--id",
            pkg_id,
            "-e",
            "--accept-source-agreements",
            "--disable-interactivity",
        ],
        check=False,
    )
    if r.returncode != 0:
        print(f"警告: winget 卸载 {pkg_id} 失败 (exit {r.returncode})")


def stop_verge() -> None:
    for name in (
        "clash-verge.exe",
        "verge-mihomo.exe",
        "verge-mihomo-alpha.exe",
        "mihomo.exe",
    ):
        subprocess.run(
            ["taskkill", "/IM", name, "/F"],
            capture_output=True,
            check=False,
        )


def start_verge(exe: Path) -> None:
    subprocess.Popen(
        [str(exe)],
        cwd=str(exe.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _tray_already_running() -> bool:
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'tray\\.py' -and $_.CommandLine -notmatch 'Get-CimInstance' } | Measure-Object | Select-Object -ExpandProperty Count",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    try:
        return int((r.stdout or "0").strip() or "0") > 0
    except ValueError:
        return False


def start_tray() -> None:
    script = ROOT / "tray.py"
    if not script.is_file():
        print(f"未找到 {script}，跳过托盘。")
        return
    if _tray_already_running():
        print("分应用托盘已在运行，不再重复启动。")
        return
    flags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    print("启动分应用托盘...")
    subprocess.Popen(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )


def set_tray_autostart(enabled: bool) -> None:
    """HKCU Run: 开机用 pythonw 静默拉起 tray.py（不弹勾选窗）。"""
    path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE)
    try:
        if enabled:
            py = Path(sys.executable)
            launcher = py.with_name("pythonw.exe")
            if not launcher.is_file():
                launcher = py
            cmd = f'"{launcher}" "{ROOT / "tray.py"}" --silent'
            winreg.SetValueEx(key, TRAY_RUN_NAME, 0, winreg.REG_SZ, cmd)
            print(f"已登记开机启动托盘: {cmd}")
        else:
            try:
                winreg.DeleteValue(key, TRAY_RUN_NAME)
                print("已取消开机启动托盘。")
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def disable_windows_system_proxy() -> None:
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        0,
        winreg.KEY_SET_VALUE,
    )
    try:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        try:
            winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, "")
        except OSError:
            pass
    finally:
        winreg.CloseKey(key)
    try:
        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(0, 39, None, 0)
        wininet.InternetSetOptionW(0, 37, None, 0)
    except (AttributeError, OSError):
        pass


def wait_verge_config(timeout: float = 45.0) -> Path:
    d = verge_config_dir()
    verge_yaml = d / "verge.yaml"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if verge_yaml.is_file():
            return d
        time.sleep(0.5)
    d.mkdir(parents=True, exist_ok=True)
    (d / "profiles").mkdir(exist_ok=True)
    return d


def normalize_exe(name: str) -> str:
    n = name.strip().strip('"')
    if not n:
        return ""
    if "\\" in n or "/" in n:
        n = Path(n).name
    if not n.lower().endswith(".exe"):
        n += ".exe"
    return n


def render_profile(st: WizardState) -> str:
    procs = []
    seen: set[str] = set()
    for raw in st.processes:
        n = normalize_exe(raw)
        if not n or n.lower() in seen:
            continue
        seen.add(n.lower())
        procs.append(n)
    proc_lines = "\n".join(f"  - PROCESS-NAME,{p},proxy" for p in procs)
    if not proc_lines:
        proc_lines = "  # （未选择进程：全部 MATCH,DIRECT）"
    socks_first = st.outbound != "http"
    group = ["upstream-socks", "upstream-http"] if socks_first else ["upstream-http", "upstream-socks"]
    group.append("DIRECT")
    group_yaml = "\n".join(f"      - {g}" for g in group)
    from tun_overlay import profile_network_prelude

    net = profile_network_prelude(st.enable_tun)
    return f"""# Generated by deploy/app-proxy-manage/install.py — re-run the wizard to update.
mixed-port: 7890
bind-address: 127.0.0.1
allow-lan: false
mode: rule
log-level: info
ipv6: false
find-process-mode: strict

{net}

dns:
  enable: true
  listen: 127.0.0.1:1053
  ipv6: false
  enhanced-mode: redir-host
  use-system-hosts: true
  nameserver:
    - system
    - 223.5.5.5
  fallback: []
  proxy-server-nameserver:
    - system
    - 223.5.5.5

proxies:
  - name: upstream-socks
    type: socks5
    server: {st.proxy_host}
    port: {st.socks_port}
    udp: true
  - name: upstream-http
    type: http
    server: {st.proxy_host}
    port: {st.http_port}

proxy-groups:
  - name: proxy
    type: select
    proxies:
{group_yaml}

rules:
  - IP-CIDR,127.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,10.0.0.0/8,DIRECT,no-resolve
  - IP-CIDR,172.16.0.0/12,DIRECT,no-resolve
  - IP-CIDR,192.168.0.0/16,DIRECT,no-resolve
  - IP-CIDR,169.254.0.0/16,DIRECT,no-resolve
  - IP-CIDR6,::1/128,DIRECT,no-resolve
  - IP-CIDR6,fc00::/7,DIRECT,no-resolve
  - IP-CIDR6,fe80::/10,DIRECT,no-resolve
{proc_lines}
  - MATCH,DIRECT
"""


def patch_verge_yaml(path: Path, st: WizardState) -> None:
    import yaml

    data = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            data = loaded
    data["enable_system_proxy"] = False
    data["enable_tun_mode"] = bool(st.enable_tun)
    data["enable_dns_settings"] = False
    data["enable_auto_launch"] = bool(st.enable_auto_launch)
    data["enable_silent_start"] = True
    data["enable_external_controller"] = True
    data["clash_core"] = data.get("clash_core") or "verge-mihomo"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Clash Verge Config\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def upsert_profiles_yaml(path: Path) -> None:
    import yaml

    data = {"current": PROFILE_UID, "items": []}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            data["items"] = list(loaded.get("items") or [])
    items = [it for it in data["items"] if isinstance(it, dict) and it.get("uid") != PROFILE_UID]
    items.insert(
        0,
        {
            "uid": PROFILE_UID,
            "type": "local",
            "name": PROFILE_NAME,
            "desc": "deploy/app-proxy-manage/install.py",
            "file": PROFILE_FILE,
            "updated": int(time.time()),
        },
    )
    data["current"] = PROFILE_UID
    data["items"] = items
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


VERGE_SERVICE_NAME = "clash_verge_service"


def _tun_service_registered() -> bool:
    r = subprocess.run(
        ["sc", "query", VERGE_SERVICE_NAME],
        capture_output=True,
        check=False,
    )
    return r.returncode == 0


def try_install_tun_service(verge_exe: Path) -> None:
    # Official installer is clash-verge-service-install.exe (one-shot, UAC).
    # clash-verge-service.exe is the IPC daemon: it listens on a named pipe and
    # never exits. Do not launch it, and do not glob *service*.exe.
    if _tun_service_registered():
        print("Clash Verge 服务已注册，跳过安装。")
        return
    installer = None
    for root in (verge_exe.parent, verge_exe.parent / "resources"):
        p = root / "clash-verge-service-install.exe"
        if p.is_file():
            installer = p
            break
    if not installer:
        print("未找到 clash-verge-service-install.exe。请在 Verge 设置 → 服务模式 点一次安装。")
        return
    print(f"安装 TUN 服务（可能弹出 UAC）: {installer}")
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Start-Process -FilePath '{installer}' -Verb RunAs -Wait",
        ],
        check=False,
    )
    if r.returncode != 0 or not _tun_service_registered():
        print("服务安装未完成。请稍后在 Verge 设置 → 服务模式 手动安装。")


def ask(st: WizardState, installed: bool) -> WizardState:
    import questionary
    from questionary import Choice

    print()
    print("MaintainAll 分应用代理向导（Clash Verge Rev）")
    print("填写上游代理后写入 Verge；勾选哪些应用走代理在随后打开的托盘里完成。")
    print()

    host = questionary.text(
        "代理主机（IP 或域名）",
        default=st.proxy_host,
        validate=lambda s: True if s.strip() and "<" not in s else "请填写 IP 或域名",
    ).ask()
    if host is None:
        raise SystemExit(1)
    st.proxy_host = host.strip()

    socks = questionary.text("SOCKS5 端口", default=str(st.socks_port)).ask()
    http = questionary.text("HTTP 端口", default=str(st.http_port)).ask()
    if socks is None or http is None:
        raise SystemExit(1)
    try:
        st.socks_port = int(socks)
        st.http_port = int(http)
    except ValueError:
        _die("端口必须是数字")
    if not (1 <= st.socks_port <= 65535 and 1 <= st.http_port <= 65535):
        _die("端口超出 1–65535")

    outbound = questionary.select(
        "默认出口协议",
        choices=[
            Choice("SOCKS5", "socks"),
            Choice("HTTP", "http"),
        ],
        default=st.outbound if st.outbound in ("socks", "http") else "socks",
    ).ask()
    if outbound is None:
        raise SystemExit(1)
    st.outbound = outbound

    tun = questionary.confirm(
        "打开 TUN？（勾选应用才能被拦到；会改路由表。"
        "脚本会关掉 Verge 默认的 DNS 劫持，局域网/Tailscale 不进 TUN。"
        "浏览器若仍超时就不要开）",
        default=False,
    ).ask()
    if tun is None:
        raise SystemExit(1)
    st.enable_tun = bool(tun)

    launch = questionary.confirm(
        "开机静默启动 Clash Verge 和分应用托盘？",
        default=st.enable_auto_launch,
    ).ask()
    if launch is None:
        raise SystemExit(1)
    st.enable_auto_launch = bool(launch)

    if installed:
        up = questionary.confirm(
            "用 winget 升级 Clash Verge Rev？",
            default=st.upgrade_verge,
        ).ask()
        if up is None:
            raise SystemExit(1)
        st.upgrade_verge = bool(up)
    else:
        st.upgrade_verge = False

    ok = questionary.confirm("按以上选择写入配置并启动？", default=True).ask()
    if not ok:
        raise SystemExit(1)
    return st


def apply_cli_overrides(st: WizardState, args: argparse.Namespace) -> WizardState:
    if args.proxy_host:
        st.proxy_host = args.proxy_host.strip()
    if args.socks_port is not None:
        st.socks_port = args.socks_port
    if args.http_port is not None:
        st.http_port = args.http_port
    if args.outbound:
        st.outbound = args.outbound
    if args.tun is True:
        st.enable_tun = True
    if args.no_tun:
        st.enable_tun = False
    if args.auto_launch is True:
        st.enable_auto_launch = True
    if args.no_auto_launch:
        st.enable_auto_launch = False
    if args.upgrade_verge:
        st.upgrade_verge = True
    return st


def print_status() -> None:
    exe = find_verge_exe()
    d = verge_config_dir()
    print(f"Clash Verge: {exe if exe else '未安装'}")
    print(f"winget:      {'已安装' if winget_has(VERGE_WINGET_ID) else '未安装'}")
    print(f"配置目录:    {d} {'(存在)' if d.is_dir() else '(尚未创建)'}")
    print(f"向导状态:    {STATE_PATH if STATE_PATH.is_file() else '无'}")
    print(f"profile:     {d / 'profiles' / PROFILE_FILE}")
    st = load_state()
    if st.proxy_host:
        print(f"上次主机:    {st.proxy_host}:{st.socks_port}/{st.http_port}")
        print(f"上次进程:    {', '.join(st.processes) or '(无)'}")


def apply(st: WizardState, *, start_app: bool, start_tray_app: bool = True) -> None:
    if not st.proxy_host or "<" in st.proxy_host:
        _die("缺少有效的代理主机")
    installed = bool(find_verge_exe()) or winget_has(VERGE_WINGET_ID)
    winget_install_or_upgrade(upgrade=st.upgrade_verge or not installed)
    exe = find_verge_exe()
    if not exe:
        _die("未找到 clash-verge.exe")

    print("关闭 Clash Verge（若在运行）以便写配置...")
    stop_verge()
    time.sleep(1)

    cfg_dir = verge_config_dir()
    if not (cfg_dir / "verge.yaml").is_file():
        print("首次配置：先启动一次 Verge 以生成目录，然后关掉再写入...")
        start_verge(exe)
        wait_verge_config()
        time.sleep(2)
        stop_verge()
        time.sleep(1)

    cfg_dir = wait_verge_config(timeout=5)
    profiles_dir = cfg_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    dest = profiles_dir / PROFILE_FILE
    if dest.is_file():
        import yaml

        from profile_rules import process_names_from_rules, unique_exes

        loaded = yaml.safe_load(dest.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            st.processes = unique_exes([*process_names_from_rules(loaded), *st.processes])
    body = render_profile(st)
    dest.write_text(body, encoding="utf-8")
    upsert_profiles_yaml(cfg_dir / "profiles.yaml")
    patch_verge_yaml(cfg_dir / "verge.yaml", st)
    from tun_overlay import patch_yaml_tun

    patch_yaml_tun(cfg_dir / "config.yaml", enable=st.enable_tun)
    patch_yaml_tun(cfg_dir / "clash-verge.yaml", enable=st.enable_tun)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "mihomo-whitelist.yaml").write_text(body, encoding="utf-8")
    save_state(st)

    print("关闭 Windows 系统代理...")
    disable_windows_system_proxy()

    if st.enable_tun:
        try_install_tun_service(exe)

    set_tray_autostart(st.enable_auto_launch)

    print()
    print(f"已写入 profile: {profiles_dir / PROFILE_FILE}")
    print("  系统代理: 关（Verge + WinINET）")
    print(f"  TUN: {'开' if st.enable_tun else '关'}")
    if st.enable_tun:
        print("  TUN DNS 劫持: 关（已改 Verge config.yaml，避免浏览器超时）")
    print(f"  开机启动: {'Verge + 分应用托盘' if st.enable_auto_launch else '关'}")
    print(f"  代理: {st.proxy_host}  socks={st.socks_port}  http={st.http_port}")
    kept = ", ".join(st.processes) if st.processes else "尚未勾选（托盘里选）"
    print(f"  进程白名单: {kept}")
    print("再运行本脚本可改主机/端口；应用勾选只在托盘里改，不会被向导清空。")
    print("勾选应用会由托盘窗口打开；也可之后再运行 python tray.py。")

    if start_app:
        print("启动 Clash Verge...")
        start_verge(exe)
        from tun_overlay import patch_yaml_tun as _ptun

        for _ in range(24):
            time.sleep(0.5)
            cfg = cfg_dir / "config.yaml"
            rt = cfg_dir / "clash-verge.yaml"
            if cfg.is_file():
                _ptun(cfg, enable=st.enable_tun)
            if rt.is_file():
                _ptun(rt, enable=st.enable_tun)
            if cfg.is_file() and rt.is_file():
                break
    if start_tray_app:
        start_tray()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Clash Verge Rev 分应用代理一键配置")
    p.add_argument("--check", action="store_true", help="只打印安装状态")
    p.add_argument("--non-interactive", action="store_true", help="用上次 wizard.json / 命令行参数，不再提问")
    p.add_argument("--proxy-host", default="", help="代理主机（IP 或域名）")
    p.add_argument("--socks-port", type=int, default=None)
    p.add_argument("--http-port", type=int, default=None)
    p.add_argument("--outbound", choices=("socks", "http"), default="")
    p.add_argument("--tun", action="store_true", default=None)
    p.add_argument("--no-tun", action="store_true")
    p.add_argument("--auto-launch", action="store_true", default=None)
    p.add_argument("--no-auto-launch", action="store_true")
    p.add_argument("--upgrade-verge", action="store_true")
    p.add_argument("--no-start", action="store_true", help="写完配置不启动 Verge")
    p.add_argument("--no-tray", action="store_true", help="写完配置不启动分应用托盘")
    return p.parse_args()


def main() -> None:
    if os.name != "nt":
        _die("当前向导只支持 Windows")
    args = parse_args()
    if args.check:
        print_status()
        return
    ensure_deps(gui=not args.no_tray)
    st = load_state()
    st = apply_cli_overrides(st, args)
    installed = bool(find_verge_exe()) or winget_has(VERGE_WINGET_ID)
    if not args.non_interactive:
        if not sys.stdin.isatty():
            _die("需要交互终端，或加上 --non-interactive 与 --proxy-host")
        st = ask(st, installed=installed)
    elif not st.proxy_host:
        _die("--non-interactive 需要已有 wizard.json 或 --proxy-host")
    apply(st, start_app=not args.no_start, start_tray_app=not args.no_tray)


if __name__ == "__main__":
    main()
