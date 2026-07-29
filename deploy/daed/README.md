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

克隆后运行引导脚本，按提示完成配置：

```bash
cd deploy/daed
python3 scripts/setup.py
```

脚本会引导你：
1. 选择本机网卡（列出所有可用接口及其 IP）
2. 逐条输入订阅链接和标签（支持多个，空行结束）
3. 设置 Web 管理面板用户名和密码
4. 自动安装 gost 和配置 systemd 服务
5. 启动 daed 和透明代理

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

# 配置订阅：复制示例文件并修改
cp config/subscriptions.txt.example config/subscriptions.txt
# 编辑 subscriptions.txt，填入你的订阅链接

# 修改网卡名：编辑 config/global.conf
# 将 <YOUR_LAN_INTERFACE> 替换为实际网卡名（ip link show 可查）

# 启动 daed
docker compose up -d

# 访问 Web UI http://localhost:2023
# 首次需要创建管理员账号，或已有 wing.db 则重置密码：
python3 scripts/reset_password.py <新密码>
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

### 导出配置（备份）

```bash
python3 scripts/export_config.py
```

导出文件保存到 `exported/` 目录：
- `global.conf` — 全局配置
- `dns.conf` — DNS 配置
- `routing.conf` — 路由规则
- `subscriptions.txt` — 订阅信息

### 恢复配置

```bash
python3 scripts/restore_config.py
docker restart daed
```

### 私有规则（分组 + URL，不入版本库）

私人分组和不想提交进 git 的地址，写进 `config/private.conf`（已在 `.gitignore` 中）。它是一个小 DSL：先定义组，再用简写规则把地址指到组：

```bash
cp config/private.conf.example config/private.conf
```

```
group work = fixed               # random|fixed|fixed(N)|min|min_avg10|min_moving_avg
group home = min_moving_avg

suffix:internal.example.com, corp.example.org -> work
keyword:myhost -> home
ip:203.0.113.10/32 -> work
domain(suffix: extra.example.com) -> proxy   # 原生 dae 规则也可直接写
```

- 匹配器：`suffix` / `full` / `keyword` / `regex` / `ip` / `geosite` / `geoip`，多个值用逗号分隔
- 目标可以是本文件定义的组、`groups.txt` 里的组，或内建 `direct` / `block` / `proxy` 等
- 空组会自动从 `proxy` 塞 1 个节点，之后在 Web UI 改成员不会被覆盖

生效（组种子 + 路由合并一次完成）：

```bash
docker compose up -d --build daed-config-sync && docker restart daed
```

机制：daed 启动前 `daed-config-sync` 展开 DSL —— 组 upsert 进 `wing.db`，规则注入 `routing.conf` 的 `# private-rules` 标记处（默认在 geo CN / fallback 之前，优先级更高）。私有地址只存在于本文件与 `wing.db`（均不入版本库）；`export_config.py` 导出的 `exported/` 也在 `.gitignore` 中。免重建镜像只补组：`python3 scripts/seed_groups.py && docker restart daed`。

### 出站分组（自动种子）

`docker compose up` 时，`daed-config-sync` 会：

1. 同步 `global.conf` / `dns.conf` / `routing.conf` 进 `wing.db`
2. 按 `config/groups.txt` **创建/更新空 Group**（不挂节点）

你只需在 Web UI → Groups 里把 sticky 组换成目标节点（或保留默认克隆的 proxy 成员）。路由已绑定好，不必再手建组名。

首次种子时若 sticky 组为空，会从 `proxy` **挑 1 个节点**塞进去（`fixed` 策略只允许单节点）。之后在面板改组成员不会被同步脚本覆盖。

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

手工补种（不重建 sync 镜像时）：

```bash
python3 scripts/seed_groups.py
docker restart daed
```

编辑 `config/groups.txt` 可增删组；改完后 `docker compose up -d --build daed-config-sync` 或跑 `seed_groups.py`，再重启 daed。

### 重置 Web UI 密码

```bash
python3 scripts/reset_password.py <新密码>
```

### 节点健康 + 出口测速

```bash
# 健康（GraphQL 列节点 + docker logs ALIVE）+ 经 gost 测 Cloudflare / GitHub
python3 scripts/bench_nodes.py

# 仅健康 / 仅吞吐
python3 scripts/bench_nodes.py --health-only
python3 scripts/bench_nodes.py --throughput-only

# 账号可用环境变量，避免交互输入
DAED_USER=admin DAED_PASS='***' python3 scripts/bench_nodes.py
```

默认经 `http://127.0.0.1:20171`（gost）拉：

- Cloudflare：`speed.cloudflare.com` 1MiB
- GitHub：`raw.githubusercontent.com/github/gitignore/.../Python.gitignore`

不修改分组策略，测的是当前选中 dialer。

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

- 国内域名 → 阿里 DNS (`223.5.5.5`)
- 其他域名 → Google DNS (`dns.google`)

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
├── docker-compose.yml              # daed Docker 容器（先跑 config-sync）
├── README.md                       # 本文档
├── .gitignore
├── config/
│   ├── global.conf                 # 全局配置
│   ├── dns.conf                    # DNS 配置
│   ├── routing.conf                # 路由规则（含 sticky outbound）
│   ├── groups.txt                  # 出站分组种子（compose 自动同步）
│   ├── subscriptions.txt.example   # 订阅信息模板
│   ├── subscriptions.txt           # 订阅信息（用户自填，不入版本库）
│   ├── private.conf.example        # 私有规则 DSL 模板
│   ├── private.conf                # 私有分组 + 规则（用户自填，不入版本库）
│   └── wing.db                     # 运行时数据库
├── gost/
│   ├── gost.service                # gost 系统级 systemd 服务
│   └── gost-user.service           # gost 用户级 systemd 服务
└── scripts/
    ├── setup.py                     # 引导式一键部署脚本
    ├── export_config.py            # 配置导出
    ├── restore_config.py           # 配置恢复
    ├── reset_password.py           # 密码重置
    ├── seed_groups.py              # 手工补种出站分组
    ├── bench_nodes.py              # 节点健康 + 出口测速
    └── daed-config-sync/           # compose 启动前同步 conf + groups
```
