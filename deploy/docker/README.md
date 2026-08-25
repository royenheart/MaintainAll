# docker 加速配置

Docker daemon 的 registry 镜像加速配置，含
[DaoCloud public-image-mirror](https://github.com/DaoCloud/public-image-mirror)
（`https://docker.m.daocloud.io`）。

## 一键配置（新机器）

```bash
python3 install.py --dry-run   # 预览最终配置（无需 root）
sudo python3 install.py        # 合并写入 /etc/docker/daemon.json 并重启 docker

# 新机器顺便指定数据目录（可选）
sudo python3 install.py --data-root /mnt/data1/docker
```

`install.py` 会：

1. 与已有的 `/etc/docker/daemon.json` 做 JSON 合并（`registry-mirrors`
   取并集、本配置优先，其余字段保留原值）；
2. 原文件备份为 `daemon.json.bak-<时间戳>`；
3. 原子写入后 `systemctl restart docker`，并用 `docker info` 打印生效的 mirrors。

无第三方依赖，系统自带 python3 即可运行。

## data-root（数据目录）

Docker **只支持一个** `data-root`，因此合并规则是**已有的优先保留**：

- 目标机器已有 `data-root` → 保留原值；若同时传了 `--data-root` 且不同，
  只会提示、不生效；
- 确认要更换 → 加 `--overwrite-data-root`；
- 没有 `data-root` → 使用 `--data-root` 指定的值。

> 注意：切换 `data-root` 不会迁移旧目录里已有的镜像 / 容器，旧数据仍留在
> 原路径，需要手工迁移或 `docker save/load`。

## 说明

- `registry-mirrors` 只对 docker.io（Docker Hub）生效；gcr.io / ghcr.io /
  quay.io 等需要用前缀替换的方式拉取，例如
  `docker pull m.daocloud.io/docker.io/library/nginx`，各 registry 的替换
  域名见上游 README。
- mirror 列表按顺序尝试，不可用的会被自动跳过。
