# deploy/proxy · sub — 把私有节点合成一个订阅（独立组件）

把一个或多个私有节点（hy2 / vless 等）组成一条 **dae 订阅 URL**，daed 只维护
"一个订阅"而不是"多份节点链接"。本组件独立：停/删 TCP 或 UDP 节点不影响订阅，
反过来亦然（详见下文"独立性"）。

## 原理

dae 的订阅 URL 只需返回 **base64 文本**：解码后每行一条分享链接（v2ray 标准 sub
格式）。不需要 subconverter / web 面板——一个静态文件即可。

## 1. 生成 base64 订阅

```bash
./scripts/make-subscription.sh import-links.txt    # -> import-links.txt.b64
```

`import-links.txt`：每行一条分享链接，`#` 注释与空行会被剥掉。

## 2. 暴露订阅 URL（推荐 HTTPS，无需额外端口）

**方案 A（推荐，当前采用）：与 VLESS 共用一个有效证书的 443 server 块。**
VLESS WS 与订阅放同一个域名 server 块（模板 `openresty/tls-server.conf.template`
：`location /vless…` + `location /sub…` + 其余 444），证书就一份、443 早就放行，
不加端口/安全组。VLESS 节点链接的 host/sni 用同一域名且**不带 allowInsecure**
（证书有效，全局 `allow_insecure` 保持 false 即可）。

```bash
# 2.1 签发证书（DNS-01 走你的 DNS 服务商，无需开 80）
certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials /root/.secrets/certbot/cloudflare.ini \
  -d <域名>
# 2.2 用 tls-server.conf.template 生成 conf.d 里的 server 块（填 __WS_PATH__/
#     __VLESS_PORT__/__SUB_PATH__/__SUB_FILE__），reload：
openresty -t && systemctl reload openresty   # 或 nginx 对应服务
# 2.3 安装续期 hook（证书轮换后自动 reload 反代 + 重启 sing-box）
install -Dm755 deploy/proxy/nginx/certbot-restart-sing-box.sh \
  /etc/letsencrypt/renewal-hooks/deploy/restart-sing-box.sh
# 2.4 验证
curl -sS https://<域名>/sub-<随机串>.b64    # 应打印单行 base64
```

> 若你想让 VLESS 与订阅**文件级分离**：为两者各配一个子域名、拆成两个 `server` 块
> （各自证书或同证书多域名），其余流程不变。

**方案 B（无域名/暂不想弄证书时的兜底）：独立 HTTP 高位端口**，单独 `server` 块
（`listen <一个自定义高位端口>`，仅暴露精确路径、其余 `return 444`），在安全组放行
该端口。内容明文过境，仅应急用，别外传 URL。

## 3. daed 侧

1. Web UI → **Subscriptions** → 添加订阅 URL；
2. cron 建议较长（如 `0 4 * * *`）或手动刷新——链接是静态的；
3. 刷新出节点后，把它们加入目标组（proxy 等），再删除手动粘贴的旧节点，
   避免凭据漂移（每次换密钥都要重新生成订阅）。

## 安全模型与轮换

- 订阅 URL **本身无账号密码**，安全性 = HTTPS 加密 + 随机不可猜路径 + 其它路径
  一律 444。**内容里嵌着节点密码/UUID**，拿到 URL 即拿到凭据——勿外传。
- 换密钥/怀疑泄露：轮换 sing-box 凭据 → 更新 import-links.txt → 重跑
  `make-subscription.sh` 覆盖静态文件 → 换一个随机路径，可选。

## 全量轮换（一条命令，在代理服务器本机跑）

把 `../scripts/rotate.sh` 放到代理服务器上（仓库 clone 后即自带），以 root 执行：
换 hy2 密码与 vless uuid → 重启 sing-box 用户服务 → 用新凭据重建 import-links.txt →
重建订阅 base64（默认覆盖原文件，订阅 URL 不变）。

```bash
# 在代理服务器上（本机，无需 SSH）；APP_USER 是持有 sing-box 用户服务的账号
sudo APP_USER=<sing-box用户> ./scripts/rotate.sh --dry-run   # 预览（只读）
sudo APP_USER=<sing-box用户> ./scripts/rotate.sh             # 正式轮换
```

跑完后 daed 侧对同一订阅 URL 点 Update 即可；若是手动导入的节点，先删除旧节点
（旧凭据已失效）再导入新链接。提前把"到该服务器 IP 的流量"在路由里设直连，
可避免 SSH/订阅抓取依赖节点存活（见总 README 架构要点）。

## 独立性（边界说明）

当前默认：VLESS 前端与订阅在**同一个**有效证书 443 server 块里（同文件、同域名），
`location /vless…` 与 `location /sub…` 各自独立 location；hy2（UDP）不经反代。

| 操作 | 影响 |
|---|---|
| 停 sing-box 的 vless/hy2 入站 | 订阅照常（只依赖反代的静态 location） |
| 删订阅的 `location /sub…` | VLESS、hy2 照常 |
| 删整个 443 server 块 | VLESS 前端与订阅一起没（共享文件/进程） |
| 停掉整个反代进程 | VLESS 前端与订阅一起挂（共享进程） |
| 停 hy2（UDP） | VLESS、订阅照常 |

需要 VLESS 与订阅**文件级分离**：为两者各配一个子域名，拆成两个 `server` 块
（同证书多域名或各自证书）；需要进程级隔离时，订阅改用独立小服务/独立端口。
| 停掉整个反代进程 | 订阅与 VLESS 一起挂（共享进程）——需进程级隔离时，订阅改用独立小服务/独立端口 |

注意：单进程 sing-box 同时承载 hy2 与 vless 两个入站时，它一挂两个节点都断；
需要进程级隔离就拆成两个 sing-box 实例。
