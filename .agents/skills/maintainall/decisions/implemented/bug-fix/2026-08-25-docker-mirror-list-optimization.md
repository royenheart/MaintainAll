# Decision: Docker 镜像加速列表按实测速度重排并清理失效项

Status: implemented — 拉取 Docker Hub 镜像长期偏慢，实测后仅保留可用镜像并把最快的华为云 SWR 放在首位。

## Problem

`deploy/docker/daemon.json` 配置了 13 个 `registry-mirrors`，但实际拉取
`alpine:3.22`（约 3.8 MB 层）耗时 19.6 秒。逐一探测发现：

- 5 个域名无法解析：`docker.cattt.net`、`docker.etcd.fun`、
  `docker.m.ixdev.cn`、`hub.mirrorify.net`；
- 2 个返回 403：`docker.apiba.cn`、`proxy.vvvv.ee`；
- 1 个 TLS 握手失败：`hub2.nat.tf`；
- 首位的 DaoCloud 虽能返回 manifest，但 blob 层下载只有约 130 KB/s，
  Docker daemon 不会因“慢”而切换下一个 host，于是每次拉取都卡在首位慢镜像上。

## Decision

`deploy/docker/daemon.json` 的 `registry-mirrors` 只保留实测可用的 3 个，
并按 blob 下载速度排序：

1. 华为云 SWR 镜像（~6.5 MB/s）
2. `hub1.nat.tf`（~0.5 MB/s）
3. DaoCloud public-image-mirror（可用但慢，作为兜底）

同时把 `install.py` 的合并策略从“`registry-mirrors` 取并集”改为
“`registry-mirrors` 以新配置覆盖”，否则旧的失效镜像会一直留在
`/etc/docker/daemon.json` 里。

## Alternatives considered

- **保留全部镜像、只把华为云提前**：失效项虽不参与成功拉取，但会让
  Docker daemon 在 fallback 时逐个尝试无效域名，延长失败路径，不采纳。
- **只保留华为云一个镜像**：速度最快，但单点故障会直接退回 Docker Hub
  官方源，保留两个慢速兜底更稳妥。
- **继续把 DaoCloud 放首位**：它可用但 blob 层当前仅约 130 KB/s，正是
  “拉取很慢”的直接原因，不采纳。

## Consequences

- 现有 `/etc/docker/daemon.json` 不会自动更新，需在新机器或本机重新执行
  `sudo python3 deploy/docker/install.py`（合并逻辑会保留已有其他字段，
  `registry-mirrors` 以新配置覆盖）。
- 已部署机器若想立即生效，需手工把 `deploy/docker/daemon.json` 的内容
  合并进 `/etc/docker/daemon.json` 后 `systemctl restart docker`。
- 镜像可用性会随时间变化；下次变慢时应重新按“manifest 可达 + blob 层
  实测速度”评估列表，而不是只测 `GET /v2/`。
