# daed 透明代理部署配置

基于 [daed](https://github.com/daeuniverse/daed) (dae + web UI) 的透明代理方案，搭配 gost 提供 SOCKS5/HTTP 代理端口共享。

## 网络拓扑

```
其他设备 (局域网)
    │
    │ HTTP/SOCKS5 代理
    ▼
┌──────────────────────────────────────┐
│  本机 <YOUR_HOST_IP>                 │
│  ┌────────────────────────────────┐  │
│  │ gost (SOCKS5:20170,            │  │
│  │       HTTP/HTTPS:20171)        │  │
│  └───────────┬────────────────────┘  │
│              │ 出站连接               │
│  ┌───────────▼────────────────────┐  │
│  │ daed eBPF 透明代理              │  │
│  │ (tproxy:12345)                 │  │
│  └───────────┬────────────────────┘  │
│              │ 通过代理节点转发       │
└──────────────┼───────────────────────┘
               ▼
         代理节点 (订阅)
```

## 快速开始

首次部署：

```bash
cd deploy/daed

# 1. （可选）如需固定网卡，编辑 config/global.conf.example 的 lan_interface 模板；
#    daed-init.py 会自动检测物理网卡 + docker0 + UP 的 br-* 并生成 config/global.conf

# 2. 启动 daed（只启动容器，不做任何同步）
docker compose up -d daed

# 3. 访问 Web UI http://localhost:2023 创建管理员账号，并添加订阅（导入节点）

# 4. 初始化：把 config/*.conf 和 groups.txt 写入 wing.db（仅此一次）
#    终端里会询问 direct / doh；非交互默认 direct。
#    国外 DoH：python3 daed-init.py init --dns-mode doh
python3 daed-init.py
docker restart daed
```

之后所有配置（节点、分组、路由、DNS、网卡）都在 Web UI 里改，面板是唯一事实源。
`daed-init.py` 只初始化空数据库；已初始化的库不会被它覆盖。

---

## 手动部署

如果不想用引导脚本，也可以手动操作。

### 1. 前置要求

```bash
# Docker（daed 运行环境）
# gost 二进制（SOCKS5/HTTP sidecar）
```

### 2. 部署 daed

```bash
cd deploy/daed

# 如需固定网卡，编辑 config/global.conf.example 的 lan_interface 模板；
# 否则 daed-init.py 会自动检测并生成 config/global.conf（本地文件，不入版本库）

# 启动 daed
docker compose up -d daed

# 访问 Web UI http://localhost:2023
# 创建管理员账号，并先添加订阅（导入节点）

# 首次启动后初始化 wing.db（仅此一次，不会覆盖面板已有配置）
python3 daed-init.py
docker restart daed

# 忘记密码可用：
docker exec daed daed resetpass
```

### 3. 安装 gost

```bash
# 下载 gost v3
curl -L "https://github.com/go-gost/gost/releases/download/v3.2.6/gost_3.2.6_linux_amd64.tar.gz" | tar xz -C /tmp

# 用户级安装（无需 sudo）
install -Dm755 /tmp/gost ~/.local/bin/gost

# 安装用户 systemd 服务
mkdir -p ~/.config/systemd/user
cp gost/gost-user.service ~/.config/systemd/user/gost.service

# 启用开机自启（免登录启动）
loginctl enable-linger
systemctl --user daemon-reload
systemctl --user enable --now gost
```

### 4. 在其他机器上使用代理

```
HTTP 代理:   <YOUR_HOST_IP>:20171
HTTPS 代理:  <YOUR_HOST_IP>:20171
SOCKS5 代理: <YOUR_HOST_IP>:20170
```

示例（将 `<YOUR_HOST_IP>` 替换为实际 IP，如 `192.168.1.100`）：
```bash
# 命令行
export http_proxy=http://<YOUR_HOST_IP>:20171
export https_proxy=http://<YOUR_HOST_IP>:20171
export all_proxy=socks5://<YOUR_HOST_IP>:20170

# curl
curl --proxy http://<YOUR_HOST_IP>:20171 https://httpbin.org/ip

# 浏览器
# 设置 > 网络 > 代理，填入对应 IP 和端口
```

---

## 配置管理

**面板是唯一事实源。** `config/*.conf` 和 `groups.txt` 只是首次初始化模板，`daed-init.py` 只在空库时写入一次；之后所有修改都在 Web UI 完成，重启 / `docker compose` 不会再覆盖面板配置。

### 初始化

```bash
# 空库时执行一次；已初始化会自动跳过
python3 daed-init.py
docker restart daed
```

初始化会写入：

- `config/global.conf` → `configs` 表（全局配置）
- `config/dns.conf` → `dns` 表（DNS 配置；`--dns-mode doh` 时改用 `dns.conf.foreign-doh`）
- `config/routing.conf` → `routings` 表（路由规则）
- `config/groups.txt` → `groups` 表（出站分组种子）

`dns` 表里只要已有记录，再跑 `init` 不会改模式，也不会重写节点、路由或全局配置。已装好的库用 `dns-mode` 切换。

### 出站分组

首次初始化时按 `config/groups.txt` 创建分组；若 sticky 组为空，会从 `proxy` 挑 1 个节点塞进去（`fixed` 策略只允许单节点）。之后在 Web UI → Groups 里增删组、改名、换节点，均不会被脚本覆盖。

| Group | 策略 | 典型用途 |
|---|---|---|
| `proxy` | `min_moving_avg` | 默认负载均衡出口 |
| `openai` | `fixed(0)` | ChatGPT / OpenAI API（地区锁） |
| `anthropic` | `fixed(0)` | Claude / Anthropic |
| `gemini` | `fixed(0)` | Google Gemini / AI Studio |
| `github` | `min_moving_avg` | GitHub / Copilot / ghproxy（稳定出口） |
| `streaming` | `min_moving_avg` | Netflix / Disney+ / Spotify |
| `telegram` | `min_moving_avg` | Telegram |
| `discord` | `fixed(0)` | Discord |
| `docker` | `fixed(0)` | Docker Hub / ghcr.io / quay.io / 容器镜像拉取（固定节点防断连） |

### 私密规则迁移（export-private / import-private）

不想进版本管理的规则和私有分组，以注释块的形式存在 `wing.db` 的 routing 文本里：

```text
# ── private-rules:start ──
# private-group: <name> | <policy> | <param>
# private-tag: <tag>
<dae routing rules>
# ── private-rules:end ──
```

迁移时：

```bash
# 旧机导出
python3 daed-init.py export-private --output private.txt

# 新机初始化后导入
python3 daed-init.py import-private --file private.txt
docker restart daed
```

`import-private` 会按 `# private-group:` 创建缺失的私有分组，并把规则块合并进 routing。`--tag` 可按标签部分导出；`--force-groups` 可覆盖已有分组策略。

### 重置 Web UI 密码

```bash
docker exec daed daed resetpass
```

### 节点健康 + 出口测速

Web UI → Nodes 可触发节点延迟测试；经 gost 的出口测速可用：

```bash
curl -x http://127.0.0.1:20171 -o /dev/null -sS -w '%{http_code} %{speed_download}\n' \
  https://speed.cloudflare.com/__down?bytes=1048576
```

---

## 配置说明

### 全局配置 (global.conf)

| 参数 | 值 | 说明 |
|---|---|---|
| `lan_interface` | `<YOUR_LAN_INTERFACE>` | 局域网网卡（通过 `ip link show` 查看） |
| `wan_interface` | `auto` | 外网网卡 |
| `tproxy_port` | `12345` | eBPF 透明代理端口 |
| `enable_local_tcp_fast_redirect` | `true` | 本地 TCP 也走代理（gost 需要） |

### DNS 配置 (dns.conf)

直连模式（默认）：

- 国内域名 → 阿里 DNS (`udp://223.5.5.5:53`)
- 其他域名 → `tcp+udp://8.8.8.8:53`
- `systemd-resolved` 保持 `must_direct`，系统解析不进 daed

### 两种解析模式

分界是谁来解析，不是 Tailscale 对 DoH。Tailscale 只是曾经占过系统 DNS 的位置。

| 模式 | 国外域名 | `fallback_resolver` | 本机 `systemd-resolved` |
|---|---|---|---|
| `direct`（默认） | `tcp+udp://8.8.8.8:53` | `223.5.5.5:53` | 不进 daed |
| `doh` | `https://8.8.8.8/dns-query`（或 `--doh-ip 1.1.1.1`） | 同一地址的 `:53` | 53 端口查询进 daed |

国内域名在两种模式下都走阿里的 UDP。`udp_check_dns` 不改：节点健康检查仍按延迟抖动，这和域名被解析成假地址是两件事。

空库初始化：

```bash
python3 daed-init.py                  # 终端里询问；非交互默认 direct
python3 daed-init.py init --dns-mode doh
python3 daed-init.py init --dns-mode doh --doh-ip 1.1.1.1
```

已经装好的库不要靠再跑 `init` 来切换。`dns-mode` 先把 `wing.db` 备成 `wing.db.bak-<时间>`，再在一个事务里改当前选中的 DNS 行、同一条全局配置里的 `fallback_resolver`，以及 `systemd-resolved` 那一行路由。失败就回滚。SQLite 正被 daed 写入时会报 `database is locked`，库文件不会写坏。改完需要 `docker restart daed` 才生效。节点、分组和其余路由行（含 private rules）不动。

```bash
python3 daed-init.py dns-mode status
python3 daed-init.py dns-mode doh
python3 daed-init.py dns-mode direct
docker restart daed
```

`dns-mode` 会用模式模板盖掉选中的那一行 DNS。Web UI 里对这一行做过的其它改动会消失；全局配置里只动 `fallback_resolver`。

DoH 用写死的 IP，dae 不会先去解析 `dns.google`。查询走 TLS，注入包改不了内容。到 `8.8.8.8:443` 或 `1.1.1.1:443` 的连接被掐断时，解析失败，而不是连到伪造地址。`fallback_resolver` 在 dae 里只能写 `ip:port`，所以它仍是明文 UDP，只是不再指向 `223.5.5.5`。主查询路径是 DoH。

### 53 端口被墙时（不是上面的 DoH 模式）

若主机出站 UDP/TCP 53 被拦，而 ICMP/HTTPS 正常，用 [`deploy/doh-dns`](../doh-dns/README.md)，不要用上面的 `doh` 模式。`config/dns.conf.doh` 把上游指到宿主机 `127.0.0.1:5353`。那套默认的 HTTPS 上游在国内，被墙的域名仍可能直接答错。

| 文件 | 说明 |
|---|---|
| `config/dns.conf` | 直连模式模板，也是 `dns.conf.normal` 的同一内容 |
| `config/dns.conf.normal` | 直连 53 上游模板 |
| `config/dns.conf.foreign-doh` | 写死 IP 的国外 DoH 模板 |
| `config/dns.conf.doh` | 53 被墙时借用 `deploy/doh-dns` 的 5353，默认不启用 |

- 初始化前：把 `config/dns.conf.doh` 复制为 `config/dns.conf`，并把 `config/global.conf` 的 `fallback_resolver` / `udp_check_dns` 改成 `127.0.0.1:5353`
- 这和 `dns-mode doh` 是两条路，不要混用

### 路由规则 (routing.conf)

- 局域网/私有 IP → 直连
- 中国大陆 IP/域名 → 直连
- 广告域名 → 屏蔽
- Apple/阿里/微软/Steam 中国 → 直连
- OpenAI / Anthropic / Gemini → 对应 sticky group
- GitHub / 流媒体 / Telegram / Discord → 对应 sticky group
- Docker / Google 等 → `proxy`（负载均衡）
- QUIC (UDP 443) → 屏蔽（降低 CPU 负载）
- 默认 → `proxy`

> `fixed` 组只能有 **1 个节点**。种子脚本会自动塞一个默认节点；请在面板换成你要固定的出口。

---

## 文件结构

```
deploy/daed/
├── docker-compose.yml              # 只启动 daed 容器
├── daed-init.py                    # 空库初始化；dns-mode 切换已有库的解析模式
├── README.md                       # 本文档
├── .gitignore
├── config/
│   ├── global.conf.example         # 全局配置模板（进入版本管理）
│   ├── global.conf                 # 由 daed-init.py 从模板生成（本地文件，不入版本库）
│   ├── dns.conf                    # 直连模式 DNS 模板
│   ├── dns.conf.normal             # 与 dns.conf 相同的直连模板
│   ├── dns.conf.foreign-doh        # 写死 IP 的国外 DoH 模板
│   ├── dns.conf.doh                # 53 被墙时借用 deploy/doh-dns，默认不启用
│   ├── routing.conf                # 路由规则模板（含 sticky outbound）
│   ├── groups.txt                  # 出站分组种子
│   ├── subscriptions.txt.example   # 订阅信息模板
│   ├── subscriptions.txt           # 订阅信息（用户自填，不入版本库）
│   └── wing.db                     # 运行时数据库（面板唯一事实源）
└── gost/
    ├── gost.service                # gost 系统级 systemd 服务
    └── gost-user.service           # gost 用户级 systemd 服务
```
