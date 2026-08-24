# ds-harness 代理服务（Caddy Docker）

本目录不再做插件管理。`deploy.py` 现在是一个简单的 dsh 反向代理部署脚本：
用 Caddy（Docker 容器，host 网络）把宿主机上的 dsh web 实例（默认只监听
`127.0.0.1`）暴露给非本机访问，代替手写 nginx 或 `ssh -L`。

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

即让 Caddy 把外部请求“担保”成 loopback 请求，这样 dsh web 的全部功能
（包括设置、凭据、打开文件等特权方法）都能通过代理使用。

**dsh 侧不需要做任何改动**：只要 dsh web 照常用
`dsh web --port <端口> --no-open` 跑在 `127.0.0.1` 上即可（这也是它的默认
行为），不需要 `--trusted-host`，不需要改 profile，也不需要绑 `0.0.0.0`。

**代价与边界**：重写后，dsh 看到的每个请求都是 loopback，代理本身成为信任
边界。dsh 没有认证层，任何能访问代理端口的人都能控制 agent/宿主机。因此：

- 只把代理绑定到可信网络：`--listen <内网IP>`，并用防火墙限制来源；
- 或只暴露给本机（`--listen 127.0.0.1`）配合 `ssh -L` 使用；
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
  与本地 CA（已 gitignore）。
- 容器以 `--restart unless-stopped`、`--network host` 运行。
- `up` 会先删除同名旧容器再启动；`reload` 则保留容器，只执行
  `caddy reload`。

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
