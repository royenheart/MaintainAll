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

### 重置 Web UI 密码

```bash
python3 scripts/reset_password.py <新密码>
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

- 国内域名 → 阿里 DNS (`223.5.5.5`)
- 其他域名 → Google DNS (`dns.google`)

### 路由规则 (routing.conf)

- 局域网/私有 IP → 直连
- 中国大陆 IP/域名 → 直连
- 广告域名 → 屏蔽
- Apple/阿里/微软/Steam 中国 → 直连
- OpenAI/GitHub/Docker/Google → 代理
- QUIC (UDP 443) → 屏蔽（降低 CPU 负载）
- 默认 → 代理

---

## 文件结构

```
deploy/daed/
├── docker-compose.yml              # daed Docker 容器
├── README.md                       # 本文档
├── .gitignore
├── config/
│   ├── global.conf                 # 全局配置
│   ├── dns.conf                    # DNS 配置
│   ├── routing.conf                # 路由规则
│   ├── subscriptions.txt.example   # 订阅信息模板
│   ├── subscriptions.txt           # 订阅信息（用户自填，不入版本库）
│   └── wing.db                     # 运行时数据库
├── gost/
│   ├── gost.service                # gost 系统级 systemd 服务
│   └── gost-user.service           # gost 用户级 systemd 服务
└── scripts/
    ├── setup.py                     # 引导式一键部署脚本
    ├── export_config.py            # 配置导出
    ├── restore_config.py           # 配置恢复
    └── reset_password.py           # 密码重置
```
