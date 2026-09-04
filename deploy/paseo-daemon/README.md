# paseo-daemon 部署

把 [Paseo](https://paseo.sh) daemon 装到本机(无桌面、走 Remote/SSH 控制的机器)并让它**开机自启**。

参考 `deploy/systemd/install-user-daemon.sh` 的同款思路；本目录对应本机的实际环境
(ASUS / `RoyenHeartAsus`，bash 登录 shell，node 走 nvm v24.14.0)。

## 为什么要这个脚本（设计背景）

1. **GUI 不会自动装、也不会自动起 daemon。** 桌面版自带 daemon 会自动拉起；但
   Remote/SSH 传输只连**已经在跑**的 daemon，官方文档明确 SSH 不负责在远端安装、
   启动或配置。所以远端必须先自己装 CLI 再启动 daemon，这不是漏了一步，是设计。
2. **`paseo daemon start` 不跨重启。** 它只是在当前用户下 detach 一个后台进程
   （写 `~/.paseo/paseo.pid` 和 `~/.paseo/daemon.log`），崩溃时内部 supervisor 会拉
   起，能熬过 SSH 断开，但**不会**注册 systemd / 开机项——机器一重启，6767 又没人
   听了，GUI 还会报同样的 socket 错误。
3. **方案：CLI + systemd --user + linger。** 用用户级 systemd 以
   `paseo daemon start --foreground` 常驻（`--foreground` 是 CLI 真实 flag，见
   [CLI docs](https://paseo.sh/docs/cli) 与上游
   [start.ts](https://github.com/getpaseo/paseo/blob/main/packages/cli/src/commands/daemon/start.ts)），
   `Restart=on-failure` 兜崩溃，`loginctl enable-linger` 兜“未登录也随开机启动”。

## 快速开始（一键）

```bash
cd deploy/paseo-daemon
./install.sh
```

脚本幂等，可反复跑；内部对应顺序：

| 步骤 | 等价命令 | 说明 |
| --- | --- | --- |
| 1 | `npm install -g @getpaseo/cli` | 仅当 `paseo` 不在 PATH 时执行 |
| 2 | 生成 `~/.config/systemd/user/paseo.service` | `ExecStart` 用解析后的真实绝对路径（nvm 软链会被 `readlink -f` 展开），并带上 node bin 的 `PATH` |
| 3 | `systemctl --user daemon-reload && systemctl --user enable --now paseo.service` | 启动前若检测到旧的 detached 实例会先 `paseo daemon stop`，避免占用 6767 |
| 4 | `loginctl enable-linger "$USER"` | 已开启则跳过 |
| 5 | 就绪探测 + `paseo daemon status` | 校验 6767 在听、Local Daemon = running |

## 校验

```bash
paseo daemon status --no-color
systemctl --user is-active paseo.service      # active
```

`paseo daemon status` 应显示 `Local Daemon: running`、`Connected Daemon: reachable`。
之后 GUI 的 Remote/SSH 连这台机器就不该再报连接/socket 错误了。

## 管理 / 卸载

```bash
systemctl --user restart paseo.service        # 重启
journalctl --user -u paseo.service -f         # systemd 日志
tail -f ~/.paseo/daemon.log                   # daemon 日志

# 卸载
systemctl --user disable --now paseo.service
rm -f ~/.config/systemd/user/paseo.service
systemctl --user daemon-reload
# (可选) npm uninstall -g @getpaseo/cli
```

## 选项

```bash
./install.sh --no-systemd   # 只做 步骤1 + `paseo daemon start`(后台进程, 不跨重启)
./install.sh --no-install   # 跳过 npm install(要求 paseo 已在 PATH)
./install.sh --dry-run      # 打印将生成的 unit / 将执行的命令, 不落盘不启动
```

## 注意事项

- **nvm shim 在 systemd 里经常找不到。** unit 的 `ExecStart` 与 `PATH` 都由脚本按
  真实路径生成，不要手改（参考文件 `paseo.service` 只是示例）。
- **daemon 的子进程环境。** daemon 会拉起 agent / 终端等子进程，它们找
  `claude`/`codex`/`opencode`/`pnpm`/`gh` 靠的是 daemon 启动时拿到的 `PATH` 等
  环境变量；systemd --user 默认不读 `~/.bashrc`。脚本已把 `~/.local/bin`、`~/bin`
  和 node bin 放进 unit 的 `PATH`；若还缺别的工具，用 drop-in 包一层登录 shell
  （注意：`bash -lc` 会继承 `.bash_profile`/`.profile` 里 `export` 的一切，含
  token / 代理 / API key）：

  ```bash
  mkdir -p ~/.config/systemd/user/paseo.service.d
  cat > ~/.config/systemd/user/paseo.service.d/10-login-env.conf <<'EOF'
  [Service]
  Environment=HOME=%h
  ExecStart=
  ExecStart=/usr/bin/bash -lc 'exec /home/royenheart/.nvm/versions/node/v24.14.0/bin/paseo daemon start --foreground'
  EOF
  systemctl --user daemon-reload
  systemctl --user restart paseo.service
  ```

  思路同 [LINUX DO: Ubuntu 上让 Paseo 开机自启，并拿到正常环境变量](https://linux.do/t/topic/2717636)
  （原文用 zsh，本机登录 shell 是 bash，故换成 `bash -lc`）。

- **`systemctl --user` 连不上 bus？** 说明当前不在真实用户会话（如 cron、某些无
  会话 SSH 的早期阶段）。先 `loginctl enable-linger "$USER"` 并在正常登录终端里跑
  `./install.sh`。

- **升级 / 换 node 版本** 后重跑一次 `./install.sh` 即可重新生成 unit 路径。

## 排障速查

| 现象 | 处理 |
| --- | --- |
| `systemctl --user status` 显示 restarting 循环 | `journalctl --user -u paseo.service -n 50` 看报错；常见是 6767 被旧 detached 实例占着，先 `paseo daemon stop` 再 `systemctl --user restart` |
| `paseo daemon status` 显示 stale_pid / unresponsive | 机器重启过而 pid 文件残留属正常；起服务后自动覆盖 |
| GUI 仍报 socket/连接拒绝 | 本机 daemon 没起来：`paseo daemon status` 确认 Local Daemon running；SSH transport 不会替你启动 |
| agent 里找不到某命令 | 见上方 drop-in 登录 shell 方案 |
