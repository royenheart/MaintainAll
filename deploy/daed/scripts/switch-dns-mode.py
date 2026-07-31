#!/usr/bin/env python3
"""
切换 daed 的 DNS 模式（normal / doh）并重新同步配置、重启 daed。

用法:
    python3 scripts/switch-dns-mode.py normal   # 直连 UDP/TCP 53 上游（默认部署）
    python3 scripts/switch-dns-mode.py doh      # 复用宿主机 doh-dns (127.0.0.1:5353)

doh 模式适用于出站 53 被拦、但 443 正常的主机（见 deploy/doh-dns）。
切换等价于: 替换 config/dns.conf 模板 + 改写 global.conf 的
fallback_resolver / udp_check_dns -> 重跑 config-sync -> 重启 daed。
"""

import filecmp
import os
import re
import shutil
import socket
import subprocess
import sys

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"

GLOBAL_DNS_PATCHES = {
    "normal": {
        "fallback_resolver": '"223.5.5.5:53"',
        "udp_check_dns": '"dns.google:53,8.8.8.8"',
    },
    "doh": {
        "fallback_resolver": '"127.0.0.1:5353"',
        "udp_check_dns": '"127.0.0.1:5353"',
    },
}


def fail(msg: str):
    print(f"{RED}[错误] {msg}{NC}")
    sys.exit(1)


def ok(msg: str):
    print(f"  {GREEN}✓{NC} {msg}")


def warn(msg: str):
    print(f"  {YELLOW}⚠{NC} {msg}")


def patch_global(conf_path: str, mode: str):
    with open(conf_path) as f:
        content = f.read()
    for key, value in GLOBAL_DNS_PATCHES[mode].items():
        content = re.sub(
            rf"^{re.escape(key)}:.*$", f"{key}: {value}", content, flags=re.M
        )
    with open(conf_path, "w") as f:
        f.write(content)


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def compose_cmd() -> list[str]:
    for cmd in (["docker", "compose"], ["docker-compose"]):
        try:
            r = subprocess.run(cmd + ["version"], capture_output=True, timeout=10)
            if r.returncode == 0:
                return cmd
        except Exception:
            continue
    fail("Docker Compose 不可用")


def resync_and_restart(proj_dir: str):
    compose = compose_cmd()
    sync = subprocess.run(
        compose + ["up", "-d", "--build", "daed-config-sync"],
        cwd=proj_dir, capture_output=True, text=True, timeout=300,
    )
    if sync.returncode != 0:
        warn(f"config-sync 失败: {sync.stderr.strip() or sync.stdout.strip()}")
        warn("请手动执行: docker compose up -d --build daed-config-sync && docker restart daed")
        return
    restart = subprocess.run(
        ["docker", "restart", "daed"], capture_output=True, text=True, timeout=120
    )
    if restart.returncode == 0:
        ok("配置已同步，daed 已重启")
    else:
        warn(f"重启 daed 失败: {restart.stderr.strip() or restart.stdout.strip()}")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("normal", "doh"):
        fail("用法: python3 scripts/switch-dns-mode.py normal|doh")
    mode = sys.argv[1]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    proj_dir = os.path.dirname(script_dir)
    config_dir = os.path.join(proj_dir, "config")
    dns_conf = os.path.join(config_dir, "dns.conf")
    normal_tpl = os.path.join(config_dir, "dns.conf.normal")
    doh_tpl = os.path.join(config_dir, "dns.conf.doh")
    global_conf = os.path.join(config_dir, "global.conf")

    for path in (normal_tpl, doh_tpl, global_conf):
        if not os.path.exists(path):
            fail(f"缺少文件: {path}")

    print(f"{CYAN}[DNS 模式] {mode}{NC}")
    if mode == "doh":
        # 备份当前生效配置为 normal 模板（若已是 doh 版则跳过），
        # 切回 normal 时不丢用户对 dns.conf 的改动
        if not os.path.exists(normal_tpl) or not filecmp.cmp(
            dns_conf, normal_tpl, shallow=False
        ):
            if filecmp.cmp(dns_conf, doh_tpl, shallow=False):
                warn("dns.conf 已是 DoH 版，跳过 normal 备份")
            else:
                shutil.copy2(dns_conf, normal_tpl)
                ok("已备份当前 dns.conf 为 dns.conf.normal")
        shutil.copy2(doh_tpl, dns_conf)
        patch_global(global_conf, "doh")
        ok("dns.conf 已切换为 DoH 上游 (127.0.0.1:5353)")
        if not port_open("127.0.0.1", 5353):
            warn("未检测到 127.0.0.1:5353 (doh-dns/dnscrypt-proxy 未运行)")
            warn("请先部署并启动 deploy/doh-dns，否则 daed 域名解析不可用")
    else:
        shutil.copy2(normal_tpl, dns_conf)
        patch_global(global_conf, "normal")
        ok("dns.conf 已恢复为直连 53 上游")

    resync_and_restart(proj_dir)


if __name__ == "__main__":
    main()
