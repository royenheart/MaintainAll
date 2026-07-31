# doh-dns — 端口 53 被拦时的可复用 DoH 方案

适用于：**ICMP/HTTPS 正常，但所有公网 DNS（UDP/TCP 53）超时** 的机器（校园网/机房出口常见）。  
通过本机 `dnscrypt-proxy` 走 **DoH（HTTPS 443）**，再用 systemd 一键开关。

```
应用 → systemd-resolved (127.0.0.53)
         → 127.0.0.1:5353  dnscrypt-proxy
              → DoH 上游（默认阿里 / DNSPod）
```

> 需要 `systemd-resolved` + `resolvectl`（Fedora / 较新 Ubuntu 等）。

## 目录

| 文件 | 作用 |
|------|------|
| `config.env.example` | 版本、监听端口、网卡等；可复制为 `config.env` |
| `dnscrypt-proxy.toml` | DoH 静态上游（可改 stamp） |
| `download.sh` | 下载官方静态包到 `vendor/` |
| `install.sh` / `uninstall.sh` | 安装 / 卸载 |
| `doh-dns.service` | systemd 单元 |
| `dohctl` | `on\|off\|status\|test` |

## 快速使用

### A. 目标机 DNS 正常（或已能解析 GitHub）

```bash
cd deploy/doh-dns
cp -n config.env.example config.env   # 可选
./download.sh
sudo ./install.sh
sudo systemctl start doh-dns
dohctl test
```

### B. 目标机 53 被拦（HTTPS 仍通）— 推荐复用路径

**1. 在一台能解析的机器上查 GitHub 相关 IP：**

```bash
./download.sh --print-lookup-cmds
# 或手动：
dig +short github.com A | head -1
dig +short objects.githubusercontent.com A | head -1
dig +short release-assets.githubusercontent.com A | head -1
```

**2. 把本目录拷到目标机后：**

```bash
cd deploy/doh-dns
sudo ./download.sh --broken-dns <github-IP> <objects-IP> [release-assets-IP]
sudo ./install.sh
sudo systemctl start doh-dns
dohctl test
```

**3. DoH 生效后删掉临时 hosts：**

```bash
sudo sed -i '/temporary for deploy\/doh-dns download/,+3d' /etc/hosts
```

也可在能下载的机器上跑 `./download.sh`，把整个目录（含 `vendor/*.tar.gz`）拷过去，目标机直接 `sudo ./install.sh`。

## 开关

```bash
sudo systemctl start doh-dns    # 开
sudo systemctl stop doh-dns     # 关（恢复启动前 DNS）
sudo systemctl enable doh-dns   # 开机自启
dohctl status
dohctl test
```

或：`sudo dohctl on|off`

## 配置

```bash
cp config.env.example config.env
# 编辑：DNSCRYPT_PROXY_VERSION / DOH_LISTEN_PORT / DOH_DNS_IFACE / ENABLE_ON_INSTALL
```

- `DOH_DNS_IFACE` 为空时自动选默认路由网卡（不写死 `eno1`）。
- 换上游：编辑 `dnscrypt-proxy.toml` 的 `[static]` / `server_names` 后重新 `sudo ./install.sh` 并 `restart`。
- 监听端口默认 `5353`，避免和 `systemd-resolved` 的 `127.0.0.53:53` 冲突。

## 卸载

```bash
sudo ./uninstall.sh
```

## 现象对照（何时用这套）

| 现象 | 是否适用 |
|------|----------|
| `ping 8.8.8.8` 通，`dig @8.8.8.8` / 国内 DNS:53 全超时 | ✅ |
| `curl --resolve host:443:IP https://host` 成功 | ✅ |
| 同网段邻机 DNS 正常，本机 53 不通 | ✅ |
| 本机防火墙 OUTPUT DROP / 完全无外网 | ❌ 先修路由/防火墙 |
| 需要 DoT(853) 且 853 通 | 可改用 resolved DoT；本套件走 DoH/443 |

## 安全说明

- 默认上游为公共 DoH（可能有日志/过滤策略），按环境替换 stamp。
- `download.sh --broken-dns` 会改 `/etc/hosts`，用完务必删除临时段。
