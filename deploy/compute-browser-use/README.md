# Remote Computer/Browser Use 部署方案

一键部署方案，将 AI Agent 的 Computer Use（桌面控制）与 Browser Use（浏览器控制）能力拆分为 **Client（本地 PC）** 和 **Server（云端）** 两部分。

---

## 架构总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                          本地 PC (Windows)                           │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Client Control Plane (cua-control-plane)         │   │
│  │                                                               │   │
│  │  ┌──────────┐ ┌───────────────┐ ┌────────────────────────┐   │   │
│  │  │ CUA Core │ │ Deterministic │ │  REST API Server       │   │   │
│  │  │ (截图/点击│ │  Ops          │ │  (FastAPI :9110)       │   │   │
│  │  │ /键盘)   │ │ (list_apps/   │ │                        │   │   │
│  │  │          │ │  open_app/    │ │  POST /api/v1/cua/*    │   │   │
│  │  │          │ │  app_info...) │ │  POST /api/v1/dops/*   │   │   │
│  │  └──────────┘ └───────────────┘ └───────────┬────────────┘   │   │
│  │                                              │                │   │
│  │  ┌────────────────────────────┐              │                │   │
│  │  │  System Tray (pystray)     │              │                │   │
│  │  │  - 连接状态                │              │                │   │
│  │  │  - 操作开关 (ON/OFF)       │              │                │   │
│  │  │  - 权限级别 (readonly/     │              │                │   │
│  │  │    full/strict)           │              │                │   │
│  │  └────────────────────────────┘              │                │   │
│  └──────────────────────────────────────────────┼────────────────┘   │
│                                                  │                   │
└──────────────────────────────────────────────────┼───────────────────┘
                                                   │ HTTPS + Token
                                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                           云端服务器                                  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     docker-compose                            │   │
│  │                                                               │   │
│  │  ┌──────────┐    ┌────────────────┐    ┌───────────────────┐  │   │
│  │  │ AstrBot  │───▶│ Hermes Bridge  │───▶│  Hermes Agent     │  │   │
│  │  │(最小部署)│    │ (消息转发服务)  │    │  (headless mode)  │  │   │
│  │  │          │    │                │    │                   │  │   │
│  │  │ 消息平台 │    │ AstrBot Plugin │    │ Agent Loop +      │  │   │
│  │  │ Pipeline │    │ → Hermes API   │    │ computer_use tool │  │   │
│  │  └──────────┘    └────────────────┘    └─────────┬─────────┘  │   │
│  │                                                   │            │   │
│  │  ┌────────────────────────────────────────────────┼────────┐   │   │
│  │  │    Client Control Server (cua-relay)           │        │   │   │
│  │  │                                                │        │   │   │
│  │  │  对外暴露为 Hermes Agent 的 CLI 命令/工具       │        │   │   │
│  │  │  (非 MCP，而是 shell 命令风格)                  │        │   │   │
│  │  │                                                │        │   │   │
│  │  │  cuactl list-apps                              │        │   │   │
│  │  │  cuactl open-app "Chrome"                      │        │   │   │
│  │  │  cuactl capture                                │        │   │   │
│  │  │  cuactl click 100 200                          │◀───────┘   │   │
│  │  │  cuactl type "hello"                           │            │   │
│  │  └──────────────────────┬─────────────────────────┘            │   │
│  │                         │ HTTPS + Token                        │   │
│  └─────────────────────────┼──────────────────────────────────────┘   │
│                            │                                          │
└────────────────────────────┼──────────────────────────────────────────┘
                             │
                             ▼
                    Client Control Plane
```

---

## 目录结构

```
deploy/compute-browser-use/
├── README.md                          # 本文档
├── docker-compose.yml                 # Server 端一键部署
├── client/                            # Client 端（本地 PC）
│   ├── cua_control_plane/
│   │   ├── __init__.py
│   │   ├── main.py                    # 入口：托盘 + API server
│   │   ├── api.py                     # FastAPI REST 接口
│   │   ├── cua_core.py               # CUA 封装层
│   │   ├── deterministic_ops.py      # 确定性操作（list_apps/open_app 等）
│   │   ├── permissions.py            # 权限控制（readonly/full/strict）
│   │   ├── tray.py                   # Windows 系统托盘
│   │   └── config.py                 # 配置管理
│   ├── requirements.txt
│   └── install.bat                    # Windows 一键安装
├── server/                            # Server 端（云端）
│   ├── hermes-bridge/                 # AstrBot → Hermes 桥接
│   │   ├── bridge_service.py         # HTTP 桥接服务
│   │   ├── astrbot_plugin/           # AstrBot 转发插件
│   │   │   └── hermes_forward.py
│   │   └── requirements.txt
│   ├── cua-relay/                     # Client Control Server
│   │   ├── relay_server.py           # 对 Hermes 暴露 CLI 命令
│   │   └── requirements.txt
│   ├── astrbot/                       # AstrBot 最小化配置
│   │   └── cmd_config.json
│   └── hermes/                        # Hermes Agent 配置
│       └── config.yaml
└── skills/                            # Hermes Skills（操作指南）
    └── cua-desktop-control/
        └── SKILL.md
```

---

## 快速开始

### Client 端（Windows 本地 PC）

```bash
cd client
install.bat                    # 安装 Python 依赖 + 启动服务
```

安装后会：
1. 注册为 Windows 自启动服务
2. 在系统托盘显示控制图标
3. 启动本地 HTTP API (`http://127.0.0.1:9110`)

### Server 端（云端 Linux）

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env：填入 CLIENT_TOKEN、LLM_API_KEY 等

# 2. 一键启动
docker compose up -d

# 3. 检查状态
docker compose ps
docker compose logs -f hermes-agent
```

---

## Client Control Plane API

| 端点 | 方法 | 说明 | 需要权限 |
|---|---|---|---|
| `/api/v1/health` | GET | 健康检查 | - |
| `/api/v1/cua/capture` | POST | 截取当前屏幕 | readonly+ |
| `/api/v1/cua/click` | POST | 鼠标点击 `{x, y, button}` | full |
| `/api/v1/cua/type` | POST | 键盘输入 `{text}` | full |
| `/api/v1/cua/press_key` | POST | 按键 `{key}` | full |
| `/api/v1/cua/move` | POST | 鼠标移动 `{x, y}` | full |
| `/api/v1/cua/scroll` | POST | 滚动 `{dx, dy}` | full |
| `/api/v1/cua/drag` | POST | 拖拽 `{from_x, from_y, to_x, to_y}` | full |
| `/api/v1/dops/list_apps` | POST | 列出系统应用 | readonly+ |
| `/api/v1/dops/app_info` | POST | 获取应用信息 `{app_name}` | readonly+ |
| `/api/v1/dops/open_app` | POST | 打开应用 `{app_name}` | full |
| `/api/v1/dops/close_app` | POST | 关闭应用 `{app_name}` | full |
| `/api/v1/dops/app_position` | POST | 获取应用窗口位置 `{app_name}` | readonly+ |

### 权限级别

| 级别 | 允许操作 |
|---|---|
| `off` | 所有请求返回 403 Access Denied |
| `readonly` | capture、list_apps、app_info、app_position |
| `full` | 上述所有 + click、type、open_app 等写操作 |
| `strict` | 同 full，但每次写操作需托盘弹窗确认（仅限 interactive session） |

---

## Hermes Agent 集成

Hermes Agent 在 headless 模式下运行（不使用其内置 gateway），通过以下方式与系统交互：

### 1. 消息通道：AstrBot → Hermes Bridge → Hermes Agent

```
IM平台 → AstrBot Pipeline → hermes_forward plugin → Hermes Bridge HTTP → Hermes Agent run_agent.py
```

### 2. Computer Use 工具：Hermes Agent → cua-relay → Client

Hermes Agent 的 `computer_use` tool 通过 `cuactl` CLI 调用 Client Control Plane：

```bash
# Hermes Agent 内部调用
cuactl --endpoint https://client-ip:9110 --token $CLIENT_TOKEN capture
cuactl click 100 200
cuactl type "Hello World"
cuactl list-apps
```

`cuactl` 是一个轻量 Python CLI，将参数转换为对 Client Control Plane 的 HTTP 请求。

---

## 安全性设计

| 层级 | 措施 |
|---|---|
| Client 网络 | 建议通过 Tailscale/ZeroTier 组网，避免直接暴露公网 |
| API 认证 | Bearer Token 认证，Client 端自生成密钥 |
| 传输加密 | HTTPS（自签证书 + 证书 pinning） |
| 权限控制 | 三级权限 + 托盘手动开关 |
| 操作审计 | 所有操作记录到本地日志 |
| Server 隔离 | 各服务容器化，仅暴露必要端口 |
| Hermes 沙箱 | 在容器内运行，限制文件系统和网络访问 |

---

## TODO: Browser Use

- [ ] 集成 open-browser-use Chrome Extension
- [ ] Client Control Plane 增加 browser API 端点
- [ ] Hermes Agent 增加 browser_use tool
- [ ] AstrBot 增加 browser skill
