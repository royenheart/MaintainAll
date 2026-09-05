# app-proxy-manage — Windows 分应用代理

给任意 SOCKS5 / HTTP 代理做一层 **Windows 分应用客户端**：不要设系统全局代理，只让指定进程走你填的代理，其余直连。上游可以是本仓库的 [daed](../daed/README.md)/gost，也可以是其它主机上的同类端口。

本目录 **不自研内核**。Windows 侧用 Clash Verge Rev（mihomo）按进程分流；域名/节点策略由**你填的那台代理**自己负责，本机不再跑一份订阅。

```
Windows 应用（无系统代理）
    │  仅白名单进程被劫持
    ▼
┌─────────────────────────────────────────┐
│  Clash Verge Rev（TUN + PROCESS-NAME）   │
│  出站：你填写的 SOCKS5 / HTTP            │
└─────────────────┬───────────────────────┘
                  │  <host>:<socks-port>
                  │  <host>:<http-port>
                  ▼
            任意上游代理
```

向导里自行填写主机和端口。**脚本不会探测或写死任何内网地址。**

---

## 调研结论：不要从零写框架

需求拆开是两件事：

1. **抓包点**：应用自己不认 `HTTP_PROXY` / WinINET，必须在系统层把 TCP/UDP 拐走。
2. **策略点**：按进程名、路径、偶尔按 PID 决定走不走代理；最好有托盘或 WebUI。

Windows **没有** Android 那种 `include-package`（只捕获名单内 App、其它进程数据包根本不进虚拟网卡）。mihomo 明确做过 [`exclude-process` 需求](https://github.com/MetaCubeX/mihomo/issues/1719)，结论是 IP 路由表认不了进程。所以只有两条成熟路：

| 路线 | 抓包方式 | 其它应用是否受影响 | WebUI | 代表项目 |
|---|---|---|---|---|
| **A. 进程重定向** | LSP / Netfilter 只挂钩名单内进程 | 基本不影响（无 TUN、无系统 DNS 劫持） | 弱（托盘 + 桌面规则窗） | **Proxifier**（商业）、ProxyCap、Netch ProcessMode |
| **B. TUN + 进程规则** | Wintun 先接管本机路由，再 `PROCESS-NAME` 分流 | 路由/DNS 会动到整机；规则写对后 **出站** 仍可默认直连 | 强（yacd / metacubexd / zashboard） | **mihomo** + Clash Verge Rev / FlClash / 裸核 |

没有第三种「成熟且专做 daed 分应用」的产品。不要在 Windows 上再跑一份订阅节点：daed 已经做透明分流。

### 方案对比（2026）

| 项目 | 维护状态 | 分应用能力 | UI | 接到 gost | 备注 |
|---|---|---|---|---|---|
| **[Proxifier](https://www.proxifier.com)** | 商业，长期维护 | exe / 路径通配 / **`pid=1234` 实例** / 目标主机+端口 | 托盘 + 规则窗口，无 WebUI | SOCKS5 `:20170` 或 HTTP `:20171` | **最贴合「不要影响其它应用」**。标准版以 TCP 为主，UDP/QUIC/游戏弱 |
| ProxyCap / SocksCap64 | 商业 / 停更 | 类似 Proxifier | 桌面 | SOCKS | SocksCap64 偏旧，UWP/新系统兼容差 |
| **[Netch](https://github.com/netchx/netch)** | 1.9.7（2022）后停更，仓库在清 1.0 等 2.0 | ProcessMode（netfilter2.sys）只劫持名单进程 | 桌面，无 WebUI | 原生 Socks5 | 能力最接近开源 Proxifier，但驱动 + 停更风险高，**不作为本仓库默认** |
| **[mihomo](https://github.com/MetaCubeX/mihomo)** | 活跃（Clash Meta 内核） | `PROCESS-NAME` / `PROCESS-PATH` / 通配 / 正则；需 TUN 才稳 | 内核 HTTP API + 任意 dashboard | `type: socks5` 指向 gost | **本目录默认可版本化方案**。Windows TUN **没有** include-process 白名单捕获 |
| **[Clash Verge Rev](https://github.com/clash-verge-rev/clash-verge-rev)** | 活跃，~10 万星 | 同上（内嵌 mihomo） | 托盘 + 内置面板；可开 External Controller 外挂 WebUI | 导入本目录 YAML 为本地 profile | 日常托盘首选；**关掉系统代理**，只用 TUN + Rule |
| **[FlClash](https://github.com/chen08209/FlClash)** | 活跃 | 同上 | Flutter 托盘，跨 Win/macOS/Linux/Android | 同上 | 多端同一套 UI 时考虑 |
| **[v2rayN](https://github.com/2dust/v2rayN)** | 活跃 | 视核心；可挂 mihomo/sing-box | 经典 Win 托盘 | 可以，但配置比 YAML 绕 | 已有 v2rayN 习惯再用，新部署不必 |
| **[sing-box](https://sing-box.sagernet.org/configuration/route/rule/)** | 活跃 | `process_name` / `process_path`（Win/Linux/macOS） | [GUI.for.SingBox](https://github.com/GUI-for-Cores/GUI.for.SingBox) 或 clash_api + dashboard | outbound socks | 与 mihomo 同属路线 B；本仓库示例用 Clash YAML，和 Verge 更顺 |
| 系统代理 / `HTTP_PROXY` | — | 不能按应用；且大量软件不认 | 系统设置 | 填 gost | **现状，正是要替换的** |

**「实例」能细到哪一步**

- 同一路径下多个 `chrome.exe`：mihomo **分不开**（规则键是进程名/路径，不是窗口）。
- 两份安装（便携版 vs 安装版）：用 `PROCESS-PATH` / `PROCESS-PATH-REGEX`。
- 正在跑的某一个 PID：只有 **Proxifier** 的 `pid=1234` 靠谱（PID 重启即变）。
- UWP / 商店应用：LSP 类（Proxifier 部分场景）常钩不住；TUN 更稳。

### 怎么选

| 你更在意 | 选 |
|---|---|
| 其它软件、公司 VPN、虚拟机完全别被碰；主要是 TCP（浏览器、IDE、IM） | **Proxifier → gost:20170**，Default = Direct |
| 要托盘 + 连接列表里看进程；能接受装 Wintun / 服务模式 | **Clash Verge Rev** + 本目录白名单 YAML |
| 要浏览器里管（WebUI），托盘可有可无 | **裸核 mihomo** + zashboard（下文） |
| UDP 游戏、QUIC、完全不认代理的客户端 | 路线 B（TUN）；Proxifier 不够 |

本目录把 **路线 B 的可复现配置** 放在根目录。路线 A 按官方 GUI 点即可。

---

## Windows 安装（向导一键配置，可重复运行）

用 **Python + questionary** 提问：代理 **IP/域名**、**SOCKS5/HTTP 端口**、是否 TUN / 开机启动。应用白名单在随后启动的托盘里勾选。不绑定 daed 或固定端口。

1. 安装或（可选）升级 Clash Verge Rev  
2. 生成并启用本地 profile（关系统代理、按你的选择开 TUN）  
3. 关掉 Windows WinINET 系统代理  
4. 启动 Verge  
5. 自动打开分应用托盘（勾选哪些应用走代理）  

**再跑一遍会覆盖同一份 profile** 的主机/端口/TUN（uid `LMaintainAll`），用上次答案当默认值。已勾选的应用会保留。日常勾选只用托盘，不要手改 YAML。

用户通常只需：

```powershell
cd deploy/app-proxy-manage
python install.py
```

写完后会拉起托盘。之后只改勾选时再运行 `python tray.py`。不要托盘时加 `--no-tray`。

```bash
python deploy/app-proxy-manage/install.py
python deploy/app-proxy-manage/install.py --check
python deploy/app-proxy-manage/install.py --non-interactive   # 用上次 wizard.json
python deploy/app-proxy-manage/tray.py                       # 只开托盘（install.py 默认已会启动）
python deploy/app-proxy-manage/tray.py --scan
python deploy/app-proxy-manage/tray.py --reload
```

依赖：`pip install -r deploy/app-proxy-manage/requirements.txt`（脚本缺库时会自己装）。需要 Python 3.11+ 和 winget。

| 产物 | 位置 |
|---|---|
| Clash Verge Rev | 开始菜单 / 托盘（内嵌内核） |
| 向导状态 | `%LOCALAPPDATA%\MaintainAll\app-proxy\wizard.json` |
| 生效 profile | `%APPDATA%\io.github.clash-verge-rev.clash-verge-rev\profiles\LMaintainAll.yaml` |
| 托盘 | `install.py` 结束后自动启动；开机启动与 Verge 开关相同（HKCU Run → `tray.py --silent`） |

不要再单独装 `mihomo.exe`，也不要两套一起开。TUN 需要 **服务模式**：向导会提权运行 `clash-verge-service-install.exe`（不是常驻的 `clash-verge-service.exe`）。失败时在 Verge 设置 → 服务模式点一次安装。

卸载：`python deploy/app-proxy-manage/uninstall.py`。

测代理（把主机和端口换成你填的）：

```powershell
curl.exe -x socks5h://<host>:<socks-port> -I -m 10 https://httpbin.org/ip
curl.exe -x http://<host>:<http-port> -I -m 10 https://httpbin.org/ip
```

本机不要同时开第二个 TUN。Verge 若要外挂浏览器面板，在设置里打开 External Controller（`127.0.0.1:9090`），再连 [zashboard](https://github.com/Zephyruso/zashboard) / [metacubexd](https://github.com/MetaCubeX/metacubexd)。日常用 Verge 连接页即可。

---

## 路线 A：Proxifier（零 TUN）

1. 安装 [Proxifier](https://www.proxifier.com/download/)。
2. Profile → Proxy Servers → Add：`SOCKS5` / 你的代理主机 / 端口（gost 默认 `20170`），Check 通过。
3. 勾选 **Resolve hostnames through proxy**（避免 DNS 泄漏到本机解析器）。
4. Profile → Proxification Rules：
   - localhost / `10.0.0.0/8` / `172.16.0.0/12` / `192.168.0.0/16` → **Direct**
   - 各应用一条：Applications 填 `Telegram.exe` 或完整路径，Action = 刚加的 gost
   - 某个已启动实例：Applications 填 `pid=1234`
   - **Default → Direct**（否则又变全局代理）
5. 关掉 Windows 系统代理。托盘常驻即可。

UWP、部分杀毒、只走 UDP 的程序若钩不住，改走路线 B。

---

## 怎么填进程

规则 **从上到下第一条命中生效**。白名单 YAML 的顺序是：本机回环与 RFC1918 → 指定进程走 `daed` → `MATCH,DIRECT`。

不要把大段 `GEOSITE`/`GEOIP` 插在进程规则前面，否则进程规则永远轮不到。域名分流留给 daed。

在 Verge / zashboard 的 **Connections** 里看真实进程名（不要猜快捷方式名字）：

| 常见软件 | 规则示例 |
|---|---|
| Telegram Desktop | `PROCESS-NAME,Telegram.exe,proxy` |
| Cursor | `PROCESS-NAME,Cursor.exe,proxy` |
| 指定安装路径的 Chrome | `PROCESS-PATH,C:\Program Files\Google\Chrome\Application\chrome.exe,proxy` |
| 路径不固定 | `PROCESS-PATH-REGEX,(?i).*\\Google\\Chrome\\Application\\chrome\.exe$,proxy` |
| 通配 | `PROCESS-NAME-WILDCARD,*telegram*,proxy` |

Windows 进程名 **带 `.exe`，大小写按任务管理器「详细信息」**。Electron 壳经常都叫 `app.exe`，这时必须用 `PROCESS-PATH`。

子进程（更新器、崩溃报告、`git.exe` 被 IDE 拉起）要单独加规则，只写父进程不够。

改进程列表：`install.py` 结束后会打开托盘勾选；之后用 `python tray.py`。刷新列表可重扫，应用到 Verge 会写 profile 并热重载。不要手改已生成的 `LMaintainAll.yaml`。Linux / macOS 托盘为 unimplemented。

---

## 行为边界（避免和「关掉全局代理」预期打架）

- **路线 A**：未挂钩进程的 TCP 与系统 DNS 保持原样。
- **路线 B**：未勾选进程出站仍是 `MATCH,DIRECT`。安装脚本会改掉 Clash Verge 自带的 `dns-hijack: any:53`（否则 Chrome 等 DNS 全进 TUN，表现为网页超时），并把局域网 / Tailscale CGNAT 排除出 TUN 路由。TUN 仍会装虚拟网卡；和公司 VPN 可能打架。网页异常时先关 TUN。域名分流留给上游代理。
- 本机 `mixed-port: 7890` 只给 **自愿** 填代理的程序（curl、部分 CLI）。不要把它再写进 Windows 系统代理。
- daed 的 `routing.conf` 会拦 QUIC（UDP 443）。游戏/实时音视频若异常，在 daed 侧放行或让该进程 `DIRECT`，不要在 Windows 再叠一层分流。

---

## 验证

1. 系统代理保持关闭。
2. 未列入规则的浏览器访问内网站点、看本机 IP，应与开 daed 前一致。
3. 白名单应用访问 `https://httpbin.org/ip`（或任意会显示出口的页），应是 daed 节点出口，不是家庭宽带。
4. 连接面板里该行的 process 与 rule 应为 `proxy`，其它进程应为 `DIRECT`。
5. 可选：在 daed 主机上看 gost/daed 日志，仅在白名单应用发流时增长。

---

## 文件

```
deploy/app-proxy-manage/
├── README.md
├── install.py                             # 一键向导（可重复运行）
├── tray.py                                # Windows 托盘：勾选应用并重载 Verge
├── win_apps.py / profile_rules.py / verge_ctl.py
├── uninstall.py
├── requirements.txt                       # questionary + PyYAML + pystray + Pillow
└── mihomo-whitelist.yaml.example          # 字段参考；生效配置由向导写入 Verge
```

macOS / Linux 客户端（若以后要做）另开小节：Linux 可继续用 daed 本机 tproxy；其它机器用 gost 端口即可，不必上 TUN。
