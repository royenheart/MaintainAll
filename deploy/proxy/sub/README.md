# deploy/proxy · sub — 把私有节点合成一个订阅（独立组件）

把一个或多个私有节点（hy2 / vless 等）组成一条 **dae 订阅 URL**，让 daed 只维护
"一个订阅"而不是"多份节点链接"。本组件是独立的：

- 不依赖 sing-box / OpenResty 的 VLESS 前端 / Hysteria2 是否在运行；
- 停掉 TCP 或 UDP 节点、或反过来只搭订阅，互不影响；
- 订阅文件更新 = 重新生成 base64 覆盖静态文件（无需任何 web 面板）。

## 原理

dae 的订阅 URL 只需返回 **base64 文本**：解码后每行一条分享链接（v2ray 标准 sub
格式）。所以不需要 subconverter / web 面板 / 常驻服务——一个静态文件即可。

## 1. 生成 base64 订阅

```bash
./scripts/make-subscription.sh import-links.txt    # -> import-links.txt.b64
```

`import-links.txt`：每行一条分享链接，`#` 注释与空行会被剥掉。
（等价手写：`grep -vE '^\s*(#|$)' import-links.txt | base64 -w0 > import-links.txt.b64`）

## 2. 暴露订阅 URL（三选一）

**A. 独立 HTTP 端口（推荐，无 TLS 校验问题，最通用）**——OpenResty/nginx 单独
`server`，与 VLESS 前端不在同一 server 块，删掉节点配置不影响订阅：

```nginx
# 存为 conf.d/sub-http.conf；listen 端口请换用你方便的高位端口并在安全组放行
server {
    listen 18080;
    server_name _;

    location = /sub-<随机串>.b64 {
        alias /var/www/sub/<随机串>.b64;   # 与文件名一致
        default_type text/plain;
    }
    location / {
        return 444;
    }
}
```

```bash
openresty -t && systemctl reload openresty
curl -sS http://127.0.0.1:18080/sub-<随机串>.b64   # 应打印单行 base64
```

**B. 挂在自己的 HTTPS 站点上**（有域名/有效证书时更隐蔽）：任意静态路径返回该文件即可。

**C. 任何静态托管**：GitHub raw（私有仓库需鉴权，不适合）、对象存储、别的 VPS 等。

> 隐私提示：内容含节点密码/UUID。纯 HTTP 会明文过境，若在意，选 B（有效证书的
> HTTPS）或给订阅换一套短命密钥并定期轮换；不要公开/分享该 URL。

## 3. daed 侧

1. Web UI → **Subscriptions** → 添加订阅 URL；
2. cron 建议较长（如 `0 4 * * *`）或关闭、手动刷新——链接是静态的，不必高频拉取；
3. 刷新出节点后，在 Groups 里把它们加入目标组（proxy 等），再删掉手动粘贴的旧节点。

## 注意

- daed 抓取订阅用的是自身 HTTP 客户端：**自签 https 可能被拒**，所以默认推荐纯
  HTTP 端口方案 A；若走 HTTPS 请用有效证书。
- 订阅刷新若重建节点导致分组失效，把 cron 拉长或手动刷新后在 Groups 里重新加一次。
