# deploy/proxy — 通用私有代理节点部署（sing-box + daed）

在任意一台有公网 IP 的 Linux 服务器上部署 **sing-box**，提供两个可导入 daed/dae 的私有节点：

| 协议 | 端口 | 传输 | 说明 |
|---|---|---|---|
| **Hysteria2** | UDP 端口（默认 443） | QUIC (h3) | 主协议，长距离/丢包场景吞吐最好，[Hysteria2](https://hy2.io/) 的 Brutal 拥塞控制适合跨境提速 |
| **VLESS + WebSocket + TLS** | TCP 443（经你的 nginx 反代） | WS over TLS | 备用协议，nginx 继续持有 443，只需你手动添加一个私密 `location` |

dae 原生支持这两种协议，见
[dae proxy protocols](https://github.com/daeuniverse/dae/blob/main/docs/en/proxy-protocols.md)。
脚本本身**不修改 nginx**，只生成 nginx 配置片段并打印，由你自行粘贴并 reload。

## 调研结论（简述）

- dae 支持 Hysteria2、VLESS(WS/TLS/gRPC/Reality)、Shadowsocks、TUIC、Juicity 等
  （[dae proxy protocols](https://github.com/daeuniverse/dae/blob/main/docs/en/proxy-protocols.md)）。
- Hysteria2 基于 QUIC，适合高丢包跨境链路，带宽利用率普遍优于 TCP 类协议
  （[Hysteria 2 vs VLESS Reality 对比](https://lunaire.app/en/blog/hysteria-2-vs-vless-reality)）。
- VLESS+Reality 是 TCP 类性能最优，但要求独占 TCP 443（需要 nginx 让位做 fallback）。
  本方案采用 **VLESS+WS+TLS 经 nginx 反代** 作为不改变 nginx 443 监听的 TCP 备线。
- 其它候选：Shadowsocks 2022 轻量但无 TLS 伪装；TUIC/Juicity 生态/维护热度略低；
  WireGuard/gost 不适合作为 daed 导入节点。最终选择 **sing-box**：单二进制同时跑两种协议，
  systemd 托管，配置统一。

## 快速开始

### 1. 只生成配置并预览（默认，不碰任何机器）

```bash
cd deploy/proxy
./scripts/deploy.sh
```

输出内容：

1. 渲染后的 `config.json`（sing-box 服务端配置）；
2. 渲染后的 nginx `location` 片段（供你手动放入自己的 TLS server block）；
3. 两条导入链接（`hysteria2://` 与 `vless://`）。

参数：

```bash
./scripts/deploy.sh \
  --ip <服务器公网IP> \
  --sni <你的域名> \
  --cert-dir <远端证书目录> \
  --hysteria-port 443 \
  --vless-port 8443 \
  --tls-port 443 \
  --version 1.14.0
```

各参数也可用环境变量：`REMOTE_IP`、`SNI_DOMAIN`、`CERT_DIR`、`HYSTERIA_PORT`、
`VLESS_PORT`、`TLS_PORT`、`SING_BOX_VERSION`。

- 不传 `--ip` 时，导入链接里的地址显示为 `__SERVER_IP__`，按需替换。
- 不传 `--sni` 时，链接里会使用 IP 并带 `allowInsecure=1`；这通常需要 daed 允许 insecure，
  更适合内网或测试场景。公网建议提供域名和有效证书。

### 2. 安装 sing-box 到远端（可选）

```bash
./scripts/deploy.sh --install \
  --host <ssh别名或主机> \
  --ip <服务器公网IP> \
  --sni <你的域名> \
  --cert-dir <远端证书目录>
```

`--install` 只做：

1. SSH 登录远端，下载/安装 sing-box 到 `${BIN_DIR}`（默认 `/usr/local/bin`）；
2. 上传渲染好的 config 到 `${CONFIG_DIR}`（默认 `/etc/sing-box`）；
3. 安装 `sing-box.service` 并 `systemctl enable --now sing-box`；
4. 若 `--cert-dir` 未提供，自动在远端生成自签名证书（Hysteria2 使用，链接带 `insecure=1`）；
5. 打印 nginx 片段与导入链接。

它**不会**修改 nginx、不会 reload nginx、不会安装 nginx 片段。nginx 相关操作由你手动完成。

SSH 参数可通过 `SSH_ARGS` 环境变量覆盖，例如：

```bash
SSH_ARGS="-F $HOME/.ssh/config -o BatchMode=yes" \
  ./scripts/deploy.sh --install --host <ssh别名> --ip <公网IP>
```

### 3. 手动配置 nginx（仅 VLESS 备用线路需要）

把脚本输出的 `location = /vless-...` 片段放进你域名的 **TLS server block**（`listen 443 ssl` 的 server 中），
然后执行：

```bash
nginx -t
systemctl reload nginx   # 或 openresty 对应的服务名
```

nginx 只负责 TLS 终止并反代 WebSocket 到本机 `127.0.0.1:8443`（`--vless-port` 可改）。

## 导入 daed

1. 打开 daed Web UI → **Nodes**。
2. 粘贴脚本输出的 `hysteria2://` 链接（主）与 `vless://` 链接（备）。
3. 在 **Groups** 里把导入的节点加入 `proxy` 组（或按需加入 sticky 组）。
4. 在 Nodes 里做延迟/健康测试，确认 `ALIVE`。
5. 本地经 gost 出口验证：

```bash
curl -x socks5://127.0.0.1:20170 -I -m 10 https://www.gstatic.com
```

## 证书与续期

- 提供 `--cert-dir` 时，Hysteria2 使用该目录下的 `fullchain.pem` / `privkey.pem`；
  证书续期后需要重启 sing-box 使其重新加载证书。
- 未提供 `--cert-dir` 时，远端安装会生成自签名证书；对应链接含 `insecure=1`。
  daed/dae 的 `allow_insecure` 为 false 时需先允许 insecure，或改用有效证书。
- 可选用 certbot deploy hook（需你的续期系统支持）：把
  `nginx/certbot-restart-sing-box.sh` 安装到 certbot 的 deploy-hook 目录，续期后自动重启 sing-box。

## 文件结构

```
deploy/proxy/
├── README.md                             # 本文档
├── .gitignore
├── sing-box/
│   ├── config.json.template              # 通用模板（占位符由 deploy.sh 渲染）
│   └── sing-box.service                  # systemd 单元
├── scripts/
│   ├── deploy.sh                         # 生成配置/链接；--install 时安装 sing-box
│   └── install.sh                        # 远端安装脚本（只装 sing-box，不碰 nginx）
└── nginx/
    ├── proxy-location.conf.template      # 输出给你的 nginx 片段模板
    └── certbot-restart-sing-box.sh       # 可选：证书续期后重启 sing-box
```

## 常见问题

- **Hysteria2 节点不 ALIVE**：确认安全组/防火墙放行对应 UDP 端口；确认密码与 `sni`/`insecure`
  与链接一致；若用自签名证书，确认 daed 允许 insecure。
- **VLESS 节点 502/404**：确认你已把输出的 nginx 片段放进正确的 TLS server block 并 reload；
  确认 `path` 与链接一致；确认 `systemctl status sing-box` 正常。
- **不想用 VLESS**：忽略 nginx 片段，只导入 `hysteria2://` 链接即可。
- **端口冲突**：Hysteria2 的 UDP 端口可通过 `--hysteria-port` 调整；sing-box 的本地 VLESS
  TCP 监听端口可通过 `--vless-port` 调整；公网 TLS 端口通过 `--tls-port` 调整。
