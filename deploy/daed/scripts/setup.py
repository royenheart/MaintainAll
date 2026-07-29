#!/usr/bin/env python3
"""
daed + gost 一键部署脚本

引导用户填写必要配置后自动部署透明代理。
"""

import getpass
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
NC = "\033[0m"

GOST_VER = "3.2.6"


def fail(msg: str):
    print(f"{RED}[错误] {msg}{NC}")
    sys.exit(1)


def info(msg: str):
    print(f"{CYAN}{msg}{NC}")


def ok(msg: str):
    print(f"  {GREEN}✓{NC} {msg}")


def warn(msg: str):
    print(f"  {YELLOW}⚠{NC} {msg}")


def check_deps():
    print(f"{CYAN}[1/8] 检查依赖...{NC}")
    for cmd in ["docker", "python3"]:
        if shutil.which(cmd) is None:
            fail(f"需要 {cmd}，请先安装。")
    ok("Docker、Python3 就绪")
    print()


def list_interfaces():
    """列出可用网卡，返回 (接口名: IPv4) 映射。"""
    print(f"{CYAN}[2/8] 检测可用网络接口...{NC}")
    print()
    print("  可用接口列表：")
    print("  " + "─" * 41)

    ifaces = {}
    try:
        out = subprocess.check_output(
            ["ip", "-br", "link", "show"], text=True, stderr=subprocess.DEVNULL
        )
    except Exception:
        fail("无法获取网卡列表，请确认 iproute2 已安装。")

    for line in out.strip().splitlines():
        parts = line.split()
        if not parts or parts[0] == "lo":
            continue
        name = parts[0]
        ip = get_iface_ip(name)
        ifaces[name] = ip
        if ip:
            print(f"  {GREEN}{name}{NC}  ({ip})")
        else:
            print(f"  {name}  (无 IPv4)")

    print("  " + "─" * 41)
    print()
    return ifaces


def get_iface_ip(iface: str) -> str:
    try:
        out = subprocess.check_output(
            ["ip", "-4", "addr", "show", iface], text=True, stderr=subprocess.DEVNULL
        )
        m = re.search(r"inet\s+([\d.]+)", out)
        return m.group(1) if m else ""
    except Exception:
        return ""


def choose_interface(ifaces: dict) -> str:
    auto = ""
    for name, ip in ifaces.items():
        if ip:
            auto = name
            break

    if auto:
        choice = input(f"  输入 LAN 网卡名 (默认 {auto}): ").strip()
        lan = choice or auto
    else:
        lan = input("  输入 LAN 网卡名: ").strip()
        if not lan:
            fail("网卡名不能为空")

    if lan not in ifaces:
        fail(f"接口 '{lan}' 不存在")
    ok(f"使用网卡: {lan}")
    print()
    return lan


def input_subscriptions(proj_dir: str) -> list[dict]:
    """引导用户输入订阅链接和标签，返回订阅列表。"""
    print(f"{CYAN}[3/8] 配置订阅...{NC}")
    print()
    subscriptions = []

    while True:
        print(f"  {GREEN}── 添加订阅 #{len(subscriptions) + 1} ──{NC}")
        link = input("  订阅链接 (空行结束): ").strip()
        if not link:
            break
        tag = input("  标签 (如 xxx): ").strip()
        if not tag:
            tag = f"sub{len(subscriptions) + 1}"
        subscriptions.append(
            {"tag": tag, "link": link, "cron": "10 */6 * * *", "enabled": "1"}
        )
        ok(f"已添加: {tag}")
        print()

    if not subscriptions:
        warn("未添加任何订阅，可稍后在 Web UI 中添加")
        yn = input("  确认跳过？[y/N]: ").strip().lower()
        if yn not in ("y", "yes"):
            return input_subscriptions(proj_dir)  # 重新输入

    print()
    return subscriptions


def write_subscriptions_txt(subscriptions: list[dict], proj_dir: str):
    """写入 config/subscriptions.txt。"""
    target = os.path.join(proj_dir, "config", "subscriptions.txt")
    with open(target, "w") as f:
        for s in subscriptions:
            f.write(f"tag={s['tag']}\n")
            f.write(f"link={s['link']}\n")
            f.write(f"cron={s['cron']}\n")
            f.write(f"cron_enable={s['enabled']}\n")
            f.write("---\n")


def update_global_conf(proj_dir: str, lan_iface: str):
    """将 global.conf 中的占位符替换为实际网卡名。"""
    print(f"{CYAN}[4/8] 写入网卡配置...{NC}")
    conf = os.path.join(proj_dir, "config", "global.conf")
    if not os.path.exists(conf):
        fail(f"找不到 {conf}")

    with open(conf) as f:
        content = f.read()

    if "<YOUR_LAN_INTERFACE>" in content:
        content = content.replace("<YOUR_LAN_INTERFACE>", lan_iface)
        with open(conf, "w") as f:
            f.write(content)
        ok(f"已将 lan_interface 设为 {lan_iface}")
    else:
        ok(f"lan_interface 已配置")

    print()


def input_admin_account() -> tuple[str, str]:
    """输入管理员账号密码。"""
    print(f"{CYAN}[5/8] 设置 daed Web 管理面板账号...{NC}")
    user = input("  输入用户名 (默认 admin): ").strip() or "admin"
    print()
    print("  (至少 6 位，需包含字母和数字)")

    while True:
        p1 = getpass.getpass("  请输入密码: ")
        p2 = getpass.getpass("  确认密码: ")
        if p1 != p2:
            warn("两次密码不一致")
            continue
        if len(p1) < 6:
            warn("密码至少 6 位")
            continue
        if not re.search(r"[a-zA-Z]", p1) or not re.search(r"\d", p1):
            warn("密码需包含字母和数字")
            continue
        break

    ok("账号已确认")
    print()
    return user, p1


def install_gost(gost_bin: str):
    """下载安装 gost 到指定路径。"""
    print(f"{CYAN}[6/8] 安装 gost (SOCKS5/HTTP 代理)...{NC}")

    arch_map = {"x86_64": "amd64", "aarch64": "arm64"}
    arch = platform.machine()
    gost_arch = arch_map.get(arch)
    if not gost_arch:
        fail(f"不支持的架构: {arch}")

    if os.path.isfile(gost_bin):
        ok(f"gost 已安装 ({gost_bin})")
        print()
        return

    url = (
        f"https://github.com/go-gost/gost/releases/download/"
        f"v{GOST_VER}/gost_{GOST_VER}_linux_{gost_arch}.tar.gz"
    )
    print(f"  下载 gost v{GOST_VER} ({gost_arch})...")

    with tempfile.TemporaryDirectory() as tmp:
        tarball = os.path.join(tmp, "gost.tar.gz")
        urllib.request.urlretrieve(url, tarball)
        with tarfile.open(tarball) as tf:
            tf.extractall(tmp)
        os.makedirs(os.path.dirname(gost_bin), exist_ok=True)
        shutil.copy2(os.path.join(tmp, "gost"), gost_bin)
        os.chmod(gost_bin, 0o755)

    ok(f"gost 安装到 {gost_bin}")
    print()


def choose_gost_mode() -> str:
    """询问用户使用哪种 systemd 模式。返回 'user' 或 'system'。"""
    print(f"{CYAN}[7/8] 配置 gost 开机自启...{NC}")
    print()
    print("  请选择 gost 服务类型：")
    print(f"    {GREEN}[1]{NC} 用户级 systemd")
    print("       免 sudo，服务在用户登录后启动")
    print("       需要 loginctl enable-linger 实现开机免登录自启")
    print(f"    {GREEN}[2]{NC} 系统级 systemd")
    print("       需要 sudo，开机即启动（推荐服务器使用）")
    print()
    while True:
        choice = input("  请选择 [1/2] (默认 1): ").strip() or "1"
        if choice == "1":
            return "user"
        elif choice == "2":
            return "system"
        print(f"  {YELLOW}请输入 1 或 2{NC}")


def setup_gost_service(proj_dir: str, mode: str):
    """根据模式配置 gost systemd 服务。"""
    if mode == "user":
        _setup_gost_user(proj_dir)
    else:
        _setup_gost_system(proj_dir)


def _setup_gost_user(proj_dir: str):
    """配置 gost 用户级 systemd 服务。"""
    user_systemd = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(user_systemd, exist_ok=True)

    src = os.path.join(proj_dir, "gost", "gost-user.service")
    dst = os.path.join(user_systemd, "gost.service")
    shutil.copy2(src, dst)

    subprocess.run(
        ["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=10
    )
    subprocess.run(
        ["systemctl", "--user", "enable", "gost"], capture_output=True, timeout=10
    )
    subprocess.run(
        ["systemctl", "--user", "restart", "gost"], capture_output=True, timeout=10
    )

    if shutil.which("loginctl"):
        subprocess.run(["loginctl", "enable-linger"], capture_output=True, timeout=10)
        ok("gost 用户服务已安装，开机自启（含免登录）")
    else:
        ok("gost 用户服务已安装")
    print()


def _setup_gost_system(proj_dir: str):
    """配置 gost 系统级 systemd 服务（需 sudo）。"""
    if shutil.which("sudo") is None:
        warn("未找到 sudo，无法安装系统级服务，退回用户级")
        _setup_gost_user(proj_dir)
        return

    # 安装二进制到 /usr/local/bin
    user_bin = os.path.expanduser("~/.local/bin/gost")
    sys_bin = "/usr/local/bin/gost"
    if os.path.isfile(user_bin) and not os.path.isfile(sys_bin):
        print("  安装 gost 到 /usr/local/bin/ (需 sudo)...")
        try:
            subprocess.run(
                ["sudo", "install", "-Dm755", user_bin, sys_bin],
                check=True, capture_output=True, timeout=30
            )
            ok("gost 已安装到 /usr/local/bin/")
        except Exception as e:
            warn(f"sudo install 失败: {e}")
            return

    # 安装 systemd 服务
    src = os.path.join(proj_dir, "gost", "gost.service")
    dst = "/etc/systemd/system/gost.service"
    print("  安装 systemd 服务 (需 sudo)...")
    try:
        subprocess.run(
            ["sudo", "cp", src, dst],
            check=True, capture_output=True, timeout=10
        )
        subprocess.run(
            ["sudo", "systemctl", "daemon-reload"],
            check=True, capture_output=True, timeout=10
        )
        subprocess.run(
            ["sudo", "systemctl", "enable", "gost"],
            check=True, capture_output=True, timeout=10
        )
        subprocess.run(
            ["sudo", "systemctl", "restart", "gost"],
            check=True, capture_output=True, timeout=10
        )
        ok("gost 系统服务已安装，开机自启")
    except Exception as e:
        warn(f"sudo 操作失败: {e}")
    print()


def wait_for_daed(timeout: int = 60) -> bool:
    """等待 daed Web 服务就绪。"""
    for _ in range(timeout // 2):
        try:
            resp = _gql_query('{"query":"{ healthCheck }"}')
            if resp and resp.get("data", {}).get("healthCheck") == 1:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _gql_query(payload: str, token: str = "") -> dict:
    """发送 GraphQL 请求。"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        "http://localhost:2023/graphql",
        data=payload.encode(),
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _compose_cmd() -> list[str]:
    """返回可用的 docker compose 命令前缀。"""
    for cmd in (["docker", "compose"], ["docker-compose"]):
        try:
            r = subprocess.run(
                cmd + ["version"], capture_output=True, timeout=10
            )
            if r.returncode == 0:
                return cmd
        except Exception:
            continue
    fail("Docker Compose 不可用")


def start_daed_and_proxy(
    proj_dir: str,
    config_dir: str,
    admin_user: str,
    admin_pass: str,
    subscriptions: list[dict],
) -> str:
    """启动 daed，创建用户，导入订阅，分组，启动代理。返回实际用户名。"""
    print(f"{CYAN}[8/8] 启动 daed...{NC}")

    os.chdir(proj_dir)
    compose = _compose_cmd()

    # 先单独拉起 daed：全新 wing.db 需由 daed 首启建表，config-sync 依赖
    # 已有 schema，直接 compose up 会因 depends_on 卡死在 config-sync 上
    try:
        subprocess.run(
            compose + ["up", "-d", "--no-deps", "daed"],
            capture_output=True,
            check=True,
            timeout=180,
        )
    except Exception:
        fail("daed 容器启动失败，请检查 docker logs daed")

    print("  等待 daed 就绪...")
    if not wait_for_daed():
        warn("daed 启动超时，请检查 docker logs daed")
        print()
        return admin_user

    ok("daed 已启动")
    time.sleep(2)

    # schema 就绪后全量 compose up：跑 config-sync 同步 conf 并种子出站分组。
    # --build 确保镜像内的 sync 脚本与仓库当前版本一致（脚本是 COPY 进镜像的）
    try:
        subprocess.run(
            compose + ["up", "-d", "--build"],
            capture_output=True,
            check=True,
            timeout=900,
        )
        ok("配置与出站分组已同步")
    except Exception:
        warn("config-sync 失败，请检查 docker logs daed-daed-config-sync-1")

    # ── 创建/登录获取 token ──
    token, admin_user = _ensure_user_and_token(config_dir, admin_user, admin_pass)
    if not token:
        warn("无法获取管理 Token，跳过自动配置")
        warn("请打开 http://localhost:2023 手动登录后配置订阅和代理")
        print()
        return admin_user

    # ── 导入订阅 ──
    print("  导入订阅...")
    old_sub_ids, existing_tags = _get_existing_ids(token, "subscriptions")
    new_sub_ids = []
    for s in subscriptions:
        if s["tag"] in existing_tags:
            warn(f"跳过重复标签: {s['tag']} (已存在)")
        else:
            sid = _import_subscription(token, s["link"], s["tag"])
            if sid:
                new_sub_ids.append(sid)
                existing_tags.add(s["tag"])
                ok(f"已导入: {s['tag']}")
    if not new_sub_ids and not old_sub_ids:
        warn("无可用订阅")
    print()

    # ── 确保 proxy 分组存在 ──
    group_id = _ensure_group(token, "proxy")
    if not group_id:
        warn("无法创建 proxy 分组")
        print()
        return admin_user

    # ── 将新导入的订阅加入到 proxy 分组 ──
    all_sub_ids = old_sub_ids + new_sub_ids
    if all_sub_ids:
        _group_add_subscriptions(token, group_id, all_sub_ids)
        ok("订阅已关联到 proxy 分组")
    print()

    # ── 订阅就位后补种 sticky 分组 ──
    # config-sync 首次运行时库里还没有节点，sticky 组为空；
    # 空组被 routing 引用会导致 dae 拒绝加载，故需再次补种
    seed_script = os.path.join(proj_dir, "scripts", "seed_groups.py")
    r = subprocess.run(
        ["python3", seed_script], capture_output=True, text=True, timeout=60
    )
    if r.returncode == 0:
        ok("sticky 分组已补种节点")
    else:
        warn(f"分组补种失败: {r.stderr.strip() or r.stdout.strip()}")

    # ── 启动代理 ──
    try:
        _gql_query('{"query":"mutation { run(dry: false) }"}', token=token)
        ok("透明代理已启动")
    except Exception:
        warn("请在 Web UI 中手动启动代理")

    print()
    return admin_user


def _ensure_user_and_token(
    config_dir: str, user: str, password: str
) -> tuple[str, str]:
    """确保用户存在，返回 (JWT token, 实际用户名)。"""
    print("  配置管理面板账号...")
    time.sleep(2)

    try:
        resp = _gql_query('{"query":"{ numberUsers }"}')
        num_users = resp.get("data", {}).get("numberUsers", 0)
    except Exception:
        num_users = 0

    token = ""
    if num_users == 0:
        print("  首次安装，创建管理员账号...")
        u = json.dumps(user)
        p = json.dumps(password)
        query = f"mutation {{ createUser(username: {u}, password: {p}) }}"
        try:
            resp = _gql_query(json.dumps({"query": query}))
            token = (resp.get("data") or {}).get("createUser", "")
        except Exception:
            pass
    else:
        print("  检测到已有账号，重置密码...")
        script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "scripts",
            "reset_password.py",
        )
        subprocess.run(["python3", script, password], capture_output=True, timeout=10)
        # 获取实际用户名
        db_path = os.path.join(config_dir, "wing.db")
        try:
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT username FROM users LIMIT 1").fetchone()
            conn.close()
            if row:
                user = row[0]
        except Exception:
            pass
        # 登录
        u = json.dumps(user)
        p = json.dumps(password)
        query = f"query {{ token(username: {u}, password: {p}) }}"
        try:
            resp = _gql_query(json.dumps({"query": query}))
            token = (resp.get("data") or {}).get("token", "")
        except Exception:
            pass

    if token:
        ok("账号已就绪")
    return token, user


def _import_subscription(token: str, link: str, tag: str) -> str:
    """导入订阅，返回 subscription ID（base64 编码）。"""
    l = json.dumps(link)
    t = json.dumps(tag)
    query = (
        f"mutation {{ importSubscription(rollbackError: false,"
        f" arg: {{ link: {l}, tag: {t} }})"
        f" {{ sub {{ id }} }} }}"
    )
    try:
        resp = _gql_query(json.dumps({"query": query}), token=token)
        data = resp.get("data") or {}
        result = data.get("importSubscription") or {}
        sub = result.get("sub") or {}
        sid = sub.get("id", "")
        if not sid:
            errors = resp.get("errors", [])
            msg = errors[0].get("message", "unknown") if errors else "no data returned"
            warn(f"导入订阅失败 ({tag}): {msg}")
        return sid
    except Exception as e:
        warn(f"导入订阅失败 ({tag}): {e}")
        return ""


def _get_existing_ids(token: str, kind: str) -> tuple[list[str], set[str]]:
    """获取已有资源 ID 列表和 (仅对 subscriptions 返回 tag 集合)。"""
    if kind == "subscriptions":
        query_field = "{ id tag }"
    else:
        query_field = "{ id }"
    try:
        resp = _gql_query(
            json.dumps({"query": f"{{ {kind} {query_field} }}"}), token=token
        )
        items = (resp.get("data") or {}).get(kind, [])
        ids = [item["id"] for item in items]
        tags = {item["tag"] for item in items if item.get("tag")}
        return ids, tags
    except Exception:
        return [], set()


def _ensure_group(token: str, name: str) -> str:
    """确保指定名称的分组存在，返回其 ID。"""
    # 先尝试查找
    n = json.dumps(name)
    try:
        resp = _gql_query(
            json.dumps({"query": f"{{ group(name: {n}) {{ id }} }}"}), token=token
        )
        gid = ((resp.get("data") or {}).get("group") or {}).get("id", "")
        if gid:
            return gid
    except Exception:
        pass

    # 不存在则创建
    n = json.dumps(name)
    query = f"mutation {{ createGroup(name: {n}, policy: min_moving_avg) {{ id }} }}"
    try:
        resp = _gql_query(json.dumps({"query": query}), token=token)
        return ((resp.get("data") or {}).get("createGroup") or {}).get("id", "")
    except Exception:
        return ""


def _group_add_subscriptions(token: str, group_id: str, sub_ids: list[str]):
    """将订阅列表加入分组。"""
    query = (
        f"mutation {{ groupAddSubscriptions("
        f'id: "{group_id}", subscriptionIDs: {json.dumps(sub_ids)}) }}'
    )
    try:
        _gql_query(json.dumps({"query": query}), token=token)
    except Exception as e:
        warn(f"关联订阅到分组失败: {e}")


def print_summary(lan_iface: str, admin_user: str):
    host_ip = get_iface_ip(lan_iface) or "<本机IP>"

    print(f"{GREEN}{'=' * 44}{NC}")
    print(f"{GREEN}  部署完成！{NC}")
    print()
    print(f"  Web 管理面板:  {CYAN}http://localhost:2023{NC}")
    print(f"                 用户名: {CYAN}{admin_user}{NC}")
    print()
    print(f"  代理端口 (本机 IP: {CYAN}{host_ip}{NC}):")
    print(f"    SOCKS5:       {CYAN}{host_ip}:20170{NC}")
    print(f"    HTTP/HTTPS:   {CYAN}{host_ip}:20171{NC}")
    print()
    print("  客户端使用示例:")
    print(f"    export http_proxy=http://{host_ip}:20171")
    print(f"    export https_proxy=http://{host_ip}:20171")
    print()
    print(f"{GREEN}{'=' * 44}{NC}")


def main():
    print(f"{GREEN}{'=' * 44}{NC}")
    print(f"{GREEN}  daed 透明代理 + gost 端口共享 一键部署脚本{NC}")
    print(f"{GREEN}{'=' * 44}{NC}")
    print()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    proj_dir = os.path.dirname(script_dir)
    config_dir = os.path.join(proj_dir, "config")

    # 1
    check_deps()

    # 2
    ifaces = list_interfaces()
    lan_iface = choose_interface(ifaces)

    # 3
    subscriptions = input_subscriptions(proj_dir)
    write_subscriptions_txt(subscriptions, proj_dir)

    # 4
    update_global_conf(proj_dir, lan_iface)

    # 5
    admin_user, admin_pass = input_admin_account()

    # 6
    install_gost(os.path.expanduser("~/.local/bin/gost"))

    # 7
    gost_mode = choose_gost_mode()
    setup_gost_service(proj_dir, gost_mode)

    # 8
    admin_user = start_daed_and_proxy(
        proj_dir, config_dir, admin_user, admin_pass, subscriptions
    )

    # 汇总（admin_user 可能已被更新为数据库中的实际用户名）
    print_summary(lan_iface, admin_user)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}已取消。{NC}")
        sys.exit(0)
