# ds-harness 代理服务（Caddy Docker）与 dsh 插件管理

`deploy.py` 一个命令只做一件事：**部署动作**（`up` / `down` / `status` /
`scan` / `reload`）用 Caddy（Docker 容器，host 网络）把宿主机上的 dsh web
实例（默认只监听 `127.0.0.1`）暴露给非本机访问，代替手写 nginx 或
`ssh -L`；**插件管理动作**（`install` / `update`）读本目录的
[`plugins.yml`](plugins.yml) 插件列表，通过 `dsh plugin` 安装/更新 dsh 插件。
两种动作互不混合，一次运行只做其中一种。

`up` 启动代理时还会在回环端口 `9097` 拉起一个独立的 Python 管理后端
（`manage.py`），Caddy 把每个代理站点的 `/manage/` 路径反代给它。管理界面
用于监控每个 dsh 实例的可达性 / sessions / 进程 / 请求量，并在 dsh 被
外部插件写坏、无法启动时，**不依赖 dsh** 地停用/启用
`dsh.profile.bundles` 里的外部插件或切到安全模式（只加载内置 bundle），
从而远程恢复 dsh。

## 为什么用 Caddy Docker

- dsh web 的 CLI 只允许 `--host 127.0.0.1`（`--host 0.0.0.0` 会被拒绝），
  默认端口 `3080`（`dsh web --port N` 可改）。
- Caddy 的 `reverse_proxy` 自动处理 WebSocket 升级，dsh 的
  `/api/events.host`、`/api/events.mux` 走 WebSocket，普通 `/api` 走
  HTTP/SSE，Caddy 都能转发。
- Docker 容器用 `--network host`，既能绑定任意代理端口，也能直接访问宿主
  机的 `127.0.0.1:<dsh-port>`；不需要为每个端口写 `-p` 映射。
- Caddyfile 由脚本生成，不需要本机安装/配置 nginx。

## 用法

```bash
cd deploy/ds-harness

python3 deploy.py up                 # 自动绑定本机 LAN IP:3080 -> 127.0.0.1:3080
python3 deploy.py up 8080:3080       # 把 dsh 3080 暴露到代理端口 8080
python3 deploy.py up 3080 3081       # 两个 dsh 实例，分别暴露在 3080 和 3081
python3 deploy.py up 8080:3080 8081:3081  # 两个实例，代理端口与 dsh 端口不同
python3 deploy.py up --auto          # 自动扫描本机 dsh web 服务并全部暴露
python3 deploy.py up 3080 --auto     # 显式端口 + 扫描发现的端口

python3 deploy.py reload 8080:3080   # 重新生成 Caddyfile 并热加载
python3 deploy.py status             # 容器状态、最近日志、Caddyfile 站点
python3 deploy.py down               # 停止并删除 dsh-proxy 容器
python3 deploy.py scan               # 只扫描，不部署
```

端口写法：`PORT` 表示代理端口与 dsh 端口相同；`PROXY:DSH` 表示代理端口与
dsh 端口不同。所以 `up 3080 8081:3081` 的意思是：

- 第一个 dsh 实例在 `127.0.0.1:3080`，代理也监听 `3080`；
- 第二个 dsh 实例在 `127.0.0.1:3081`，代理监听 `8081`（`8081:3081` 冒号前
  是代理端口，冒号后是 dsh 端口）。

如果两个实例的代理端口和 dsh 端口相同，直接写 `up 3080 3081` 即可。
`--dry-run` 只打印将要执行的 docker 命令和生成的 Caddyfile。

## dsh 插件管理（plugins.yml）

`plugins.yml` 是插件列表，每行一个远程安装 spec：npm 包名（可带版本/tag）
或 Git/GitHub 仓库地址：

```yaml
plugins:
  - "@royenheart/dsh-plugin-foo"                 # npm：装最新版
  - "@royenheart/dsh-plugin-bar@^1.2.0"          # npm：装指定范围
  - "https://github.com/royenheart/dsh-plugin-baz"   # GitHub：HTTPS 直装
  - "github:royenheart/dsh-plugin-qux"           # GitHub：简写
```

```bash
python3 deploy.py install                    # 安装 plugins.yml 里的全部插件
python3 deploy.py update                     # 更新 plugins.yml 里的全部插件
python3 deploy.py update @royenheart/dsh-plugin-foo   # 只更新指定插件
python3 deploy.py install --profile web --dry-run     # 只看将执行的 dsh/pnpm 命令
```

安装策略：

1. **远程直装**：`dsh plugin --profile <profile> add <spec>`，npm 包和
   Git/GitHub 地址都先走这一步。
2. **本地兜底**：只有远程直装失败时，才把插件拉取到临时目录——Git 仓库用
   `git clone`，npm 包用 `npm pack`——然后 `dsh plugin add file:<临时目录>`
   安装，装完立即删除临时目录。

更新策略：

- npm 包：先检查 profile 里已安装，再 `dsh plugin update --latest <包名>`
  （更新到最新版）；未安装或更新失败时回退到上面的安装流程。
- Git/GitHub 仓库：直接重跑远程直装流程（`pnpm add` 会重新解析到最新
  commit），失败同样走本地兜底。

插件管理动作只识别 `--profile`（默认 `$DSH_PROFILE` 或 `web`）、`--home`
（默认 `$DSH_HOME` 或 `~/.dsh`）、`--dsh`（默认 PATH 里的 `dsh`）和
`--dry-run`；部署参数（`--auto`/`--listen`/`--preserve-host`/`--tls`）与
插件管理互斥，反之亦然。

## /manage 管理界面（监控与恢复）

`up` / `reload` 会把每个代理站点的 `/manage/` 路由到本目录 `manage.py`
启动的回环管理后端（默认 `127.0.0.1:9097`，可用 `--manage-port` 修改）。
访问方式：

```text
http://<代理IP>:<代理端口>/manage/       # 例如 http://192.168.31.143:3080/manage/
https://<代理IP>:<代理端口>/manage/      # --tls 模式
```

`manage.py` 不依赖 dsh 运行：dsh 起不来时，管理界面照常工作。每个实例
一张卡片，监控项独立采集，单项失败只降级该项卡片：

| 监控项 | 来源 | 失败时 |
| --- | --- | --- |
| dsh web 可达性 | `GET 127.0.0.1:<port>/` + `__DSH_BOOT__` 标记 | 显示不可达与原因 |
| sessions | 统计 `$DSH_HOME/sessions/` 下的会话目录数 | 显示不可用与原因 |
| 进程 | `ss -ltnp` 找监听 PID，`ps` 取 CPU/内存/运行时长 | 显示无进程或原因 |
| 流量 | Caddy 写入 `data/logs/access-<端口>*.json` 的 JSON 访问日志 | 显示尚无日志 |

外部加载控制（每次修改都写入 profile，**重启对应 dsh 后生效**）：

- **单个插件启用/停用**：修改 `$DSH_HOME/profiles/<profile>/package.json`
  的 `dsh.profile.bundles`。停用不删依赖、不跑 pnpm，因此插件自身
  `cordis.patch.yml` 损坏或包目录不可读时也能恢复；启用前会校验该依赖
  确实声明了 `dsh.bundle`，避免把普通库塞进 bundles。
- **实例安全模式**：一键把 `dsh.profile.bundles` 收窄为内置 bundle
  （`@deepseek-ai/dsh-base` + 对应 surface 的 bundle），并记住之前的列表；
  关闭安全模式时恢复。

恢复流程示例：插件装坏 → dsh 无法启动 → 浏览器打开 `/manage/` →
在对应实例卡片里停用该插件（或开安全模式）→ 按卡片上的启动参数重启 dsh
→ 点「进入 dsh」。多个 dsh 实例各用独立 `DSH_HOME` 时，请编辑
[`instances.yml`](instances.yml) 声明每个实例的 `port` / `profile` / `home`；
留空则回退为默认实例（3080 / web / ~/.dsh）并尝试从生成的 Caddyfile
读取端口映射。

## 代理层加载优化

不改 dsh、不改插件，生成 Caddyfile 时在代理层做了三件事：

1. **压缩**：`encode zstd gzip` 作用于除 `/api/events.host`、`/api/events.mux`
   以外的所有响应。dsh 自身不压缩，session 列表这类大 JSON 和前端 bundle
   在代理层会被压缩后再发出，实测 760KB 的 JSON 可压到约 94KB（gzip）。
2. **静态资源长缓存**：`/plugins/*`、`/assets/*`、`/favicon.svg` 响应头加
   `Cache-Control: public, max-age=31536000, immutable`。dsh 的前端资源都带
   `?rev=<hash>`，内容变了 URL 就变，长缓存安全，二次进入不用重新下载。
3. **HTML/API 强制新鲜**：`/` 和 `/api/*` 响应头加 `Cache-Control: no-cache`，
   保证每次进入拿到最新会话状态，同时仍可被压缩（事件流除外）。

这些只影响 Caddyfile 生成结果，`reload` 即可热加载；TLS 模式下 Caddy 本身
已启用 HTTP/2，多路复用对大量静态资源请求也有帮助。

### 监听地址与同端口冲突

Caddy 的站点地址（`http://:3080`）默认绑定通配地址 `0.0.0.0`，这会和
`127.0.0.1:3080` 上已运行的 dsh 冲突。因此脚本默认 `--listen` 取本机
**默认路由出口的第一个非回环 IPv4**（如 `192.168.31.143`），并给每个站点
生成 `bind <该IP>`：这样 caddy 只绑 LAN IP，和 dsh 的回环监听可以共用同一
端口，`up` 不加参数也能直接工作。

```bash
python3 deploy.py up --listen 127.0.0.1   # 只允许本机访问代理
python3 deploy.py up --listen 0.0.0.0     # 所有网卡；若与 dsh 回环端口相同会报错
python3 deploy.py up --listen 192.168.31.143 --listen 100.73.239.52  # 同时绑定多个 IP
```

`--listen` 可以重复传入，绑定多个 IP：HTTP 模式下每个站点生成一个
`bind IP1 IP2`；TLS 模式下为每个 IP 生成一个站点块，各自签发对应 IP 的证书，
代理端口相同。默认（不传 `--listen`）仍取第一个非回环 IPv4。

`--listen 0.0.0.0` 且代理端口与 dsh 回环端口相同时，脚本会在启动前检测并
报错，提示你改用 `--listen <本机IP>` 或换代理端口（如 `up 8080:3080`）。

## HTTPS 与 crypto.randomUUID

通过 `http://<LAN IP>:<端口>` 访问时，浏览器把页面视为**非安全上下文**，
`crypto.randomUUID` 不可用，dsh 前端就会报
`crypto.randomUUID is not a function`。解决方式是走 HTTPS：

```bash
python3 deploy.py up --tls                # https://<LAN IP>:3080 -> 127.0.0.1:3080
python3 deploy.py up 8443:3080 --tls      # https://<LAN IP>:8443 -> 127.0.0.1:3080
```

`--tls` 会给每个站点生成 `tls internal`，由 Caddy 自建本地 CA 签发证书；
同时生成显式的 HTTP→HTTPS 跳转站点，监听标准 HTTP 端口 80：

```caddyfile
{
    auto_https disable_redirects
}

https://192.168.31.143:8443 {
    bind 192.168.31.143
    tls internal
    reverse_proxy 127.0.0.1:3080 {
        header_up Host 127.0.0.1:3080
        header_up Origin http://127.0.0.1:3080
    }
}

http://192.168.31.143:80 {
    bind 192.168.31.143
    redir https://{host}:8443{uri} 308
}
```

这样浏览器访问 `http://<LAN IP>/`（80 端口）会自动 308 跳转到
`https://<LAN IP>:<代理端口>/`。注意：Caddy 不能在**同一个端口**上同时监听
HTTP 和 HTTPS，因此带端口的 `http://<LAN IP>:<代理端口>` 不会跳转（返回
400），请直接使用 `https://` 或去掉端口走 80 跳转。

如果同一个监听 IP 上暴露了多个代理端口（例如 `up 3081 3082 --tls`），
80 端口的 HTTP 请求已经不再携带目标端口，无法区分要跳转到哪个代理端口；
此时脚本把 80 端口跳转到**第一个映射**的代理端口，其余端口请直接用
`https://<IP>:<端口>/` 访问。若 `up` 检测到 80 端口已被占用，会跳过
HTTP→HTTPS 跳转站点（仅 HTTPS）并打印警告。

- 第一次访问浏览器会提示证书不受信任（本地 CA 未加入信任库），点
  “高级/继续访问”即可；页面成为安全上下文后 `crypto.randomUUID` 就正常了。
- 想消除警告，把 Caddy 本地根证书加入系统/浏览器信任库。证书和 CA 持久化在
  `deploy/ds-harness/data/`（容器内 `/data`），导出根证书：

  ```bash
  docker cp dsh-proxy:/data/caddy/pki/authorities/local/root.crt dsh-local-ca.crt
  ```

  然后把 `dsh-local-ca.crt` 安装到客户端机器的“受信任的根证书颁发机构”。
- 或者使用你有域名时的 Caddy 自动 HTTPS（需要自己改 Caddyfile 用域名 +
  Let's Encrypt）。
- `--tls` 需要具体的 `--listen <IP>`（默认自动探测的 LAN IP 即可），
  `--listen 0.0.0.0` 与 `tls internal` 不兼容，脚本会直接报错。

常用参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--auto` | 关 | 扫描 `127.0.0.1`/通配地址上监听的服务，命中 dsh web 标记（`__DSH_BOOT__`）则自动加入映射 |
| `--listen HOST` | 第一个非回环 IPv4（无则 `0.0.0.0`） | 代理监听地址，可重复传多个；只允许本机用 `--listen 127.0.0.1` |
| `--preserve-host` | 关 | 不重写 `Host`/`Origin` 头（见下） |
| `--tls` | 关 | 代理端口走 HTTPS（Caddy 本地 CA，修复 `crypto.randomUUID`） |
| `--container` | `dsh-proxy` | Caddy 容器名 |
| `--image` | `caddy:2` | Caddy 镜像 |
| `--manage-port` | `9097` | `/manage` 管理后端回环监听端口 |

## Host/Origin 重写与 dsh 的信任栅栏

dsh 的 `/api` 有浏览器信任栅栏（DNS-rebinding / 跨站防御）：

- 非 loopback 的 `Host` 头默认一律 403；
- `settings`、`credentials`、`host.openPath` 等特权方法**即使在 dsh 启动时
  加了 `--trusted-host` 也仍然只允许 loopback**；
- `Origin`（浏览器携带时）必须与 `Host` 完全同源。

因此脚本默认给每个站点生成（`--listen` 为具体 IP 时多一行 `bind`）：

```caddyfile
http://:8080 {
    bind 192.168.31.143
    reverse_proxy 127.0.0.1:3080 {
        header_up Host 127.0.0.1:3080
        header_up Origin http://127.0.0.1:3080
    }
}
```

即让 Caddy 把外部请求“担保”成 loopback 请求，这样 dsh web 的 API——包括
`settings.describe` / `settings.mutate` / `credentials.describe` 这些特权
方法——在服务端都能通过代理使用。

**但设置页面在远程浏览器里仍然不可用**：dsh 客户端在启动时用
`location.hostname` 判断是否 loopback。通过
`http(s)://<LAN IP>:<代理端口>` 访问时它不是 loopback，`ui-settings` 会进入
memory 模式，主动不发起 `settings.describe`。因此“设置 → 模型设置”会显示
`settings are unavailable in this browser`，凭据、设置编辑等页面同样被禁用。
这是 dsh 客户端的刻意行为（远程浏览器无认证，不允许读/写设置），不是
Caddy 漏代理；重写 Host/Origin 只影响服务端信任栅栏，改不了浏览器的
`location.hostname`。

`deploy.py up` / `reload` 会探测 dsh 实际服务的
`dsh-client-ui-settings` bundle：如果其中仍包含这个 loopback 门禁，就打印
上述提示；如果 dsh 未启动导致无法探测，会打印“无法确认”的提示；如果未来
dsh 移除了门禁（设置页可经反代使用），则不打印设置可用性提示。

**要使用完整设置页面的访问方式**：

- 本机访问：直接访问 dsh 本来的回环 URL（如 `http://127.0.0.1:3080/`），
  不要走 LAN 代理。
- 远程访问：代理用 `--listen 127.0.0.1` 并配合 SSH 本地端口转发，让浏览器
  的 URL 仍是回环地址：

  ```bash
  # 服务器：只把代理绑在回环
  python3 deploy.py up --listen 127.0.0.1
  # 客户端：把服务器回环端口转发到本机
  ssh -L 3080:127.0.0.1:3080 <服务器>
  # 客户端浏览器访问 http://127.0.0.1:3080/ —— 设置页可用
  ```

- 或者在本机/SSH 会话里用 curl 等回环客户端直接请求
  `http://127.0.0.1:<dsh-port>/api/...`；设置 API 本身经 Host 重写代理也能
  工作，只是浏览器页面会主动禁用设置 UI。

**dsh 侧不需要做任何改动**：只要 dsh web 照常用
`dsh web --port <端口> --no-open` 跑在 `127.0.0.1` 上即可（这也是它的默认
行为），不需要 `--trusted-host`，不需要改 profile，也不需要绑 `0.0.0.0`。

**代价与边界**：重写后，dsh 看到的每个请求都是 loopback，代理本身成为信任
边界。dsh 没有认证层，任何能访问代理端口的人都能控制 agent/宿主机。因此：

- 只把代理绑定到可信网络：`--listen <内网IP>`，并用防火墙限制来源；
- 或只暴露给本机（`--listen 127.0.0.1`）配合 `ssh -L` 使用（完整设置页也
  需要这种方式，见上）；
- 需要认证时在生成的 Caddyfile 里给站点加 `basic_auth`（见 Caddy 文档），
  然后 `deploy.py reload` 前把它加进本目录的 Caddyfile 模板/生成逻辑。

如果你更想保留 dsh 自己的信任栅栏，可用 `--preserve-host` 生成不重写头的
Caddyfile；此时 dsh 必须以
`dsh web --port N --trusted-host <外部host或IP>:<代理端口> --no-open` 启动，
且特权方法仍然只对 loopback 放行（通过代理访问设置/凭据会 403）。

## 自动扫描

`--auto` / `scan` 通过 `ss -ltnH` 枚举本机 loopback/通配地址上的 TCP 监听
端口，对每个端口做一次短超时的 `GET /` 探测，响应体包含 dsh web 的
`__DSH_BOOT__` 标记即认定为 dsh 服务。探测会跳过响应头 `Server: Caddy` 的
端口，避免把本代理自己扫进去。dsh web 默认端口 `3080`、`--port 0` 由系统
分配端口等场景都能覆盖，因为扫描看的是实际监听端口而不是命令行参数。

## 容器与文件

- 脚本在 `deploy/ds-harness/Caddyfile` 生成 Caddyfile，并以目录只读挂载进
  容器的 `/etc/caddy`；`data/` 目录挂载到容器 `/data`，用于持久化 TLS 证书
  与本地 CA、Caddy JSON 访问日志（`data/logs/access-*.json`）、manage 后端
  日志与 pid（`data/manage.log`、`data/manage.pid`）、manage 状态
  （`data/manage-state.json`）（均已 gitignore）。
- 容器以 `--restart unless-stopped`、`--network host`、`--user <当前用户>`
  和 `--cap-add NET_BIND_SERVICE` 运行：Caddy 写出的日志和 TLS 存储属于当前
  用户，manage 才能直接读取。从旧版（root 运行 Caddy）升级时，请重跑一次
  `up`（不是 `reload`）：脚本会把旧的 `data/caddy` 改名保留并生成新的内部
  CA，客户端需要重新信任一次新的根证书。
- `up` 会先删除同名旧容器再启动，并拉起 `manage.py`；`reload` 保留容器，
  执行 `caddy reload` 并确保 manage 后端在运行；`down` 删除容器并停止
  manage 后端。

## dsh web 实例启动参考

默认代理模式下，dsh 侧保持原样即可：

```bash
dsh web --port 3080 --no-open
dsh web --port 3081 --no-open
```

多个 dsh web 实例建议各用独立的 `DSH_HOME`（例如
`DSH_HOME=~/.dsh-3080 dsh web --port 3080 --no-open`），否则它们会共享同一
份 sessions/settings/storages，管理上容易互相干扰；代理脚本本身不依赖
`DSH_HOME`，只按端口转发。

仅当你使用 `--preserve-host` 代理模式时，dsh 才需要额外参数：

```bash
dsh web --port 3080 --no-open --trusted-host 192.168.1.10:8080
```

且该模式下 `settings`/`credentials` 等特权方法仍只对 loopback 放行。
