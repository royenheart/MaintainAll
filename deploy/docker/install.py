#!/usr/bin/env python3
"""一键配置 Docker registry 镜像加速（含 DaoCloud public-image-mirror）。

用法：
    sudo python3 install.py              # 合并写入 /etc/docker/daemon.json 并重启 docker
    python3 install.py --dry-run         # 只打印最终配置，不改任何文件
    python3 install.py --dst /tmp/x.json # 指定目标路径（测试用）

行为：
    1. 与已有的 daemon.json 做 JSON 合并：registry-mirrors 以本配置覆盖，
       其余字段（如 data-root）保留原值；
    2. 原文件备份为 daemon.json.bak-<时间戳>；
    3. 原子写入后重启 docker.service，并用 docker info 打印生效的 mirrors。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent / "daemon.json"


def merge(src: Path, dst: Path) -> dict:
    new = json.loads(src.read_text(encoding="utf-8"))
    merged: dict = {}
    if dst.exists():
        try:
            merged = json.loads(dst.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            sys.exit(f"ERROR: 现有 {dst} 不是合法 JSON，请先人工处理")

    # 新配置覆盖同名字段，其余字段保留现有值（如 data-root）。
    # registry-mirrors 也直接覆盖：旧列表常含已失效镜像，取并集会让
    # Docker 在回退时逐个尝试无效域名，拖慢失败路径。
    merged.update(new)
    return merged


def restart_docker() -> None:
    if not shutil.which("systemctl"):
        print("未找到 systemctl，请手动重启 docker 使配置生效")
        return
    units = subprocess.run(
        ["systemctl", "list-unit-files", "docker.service"],
        capture_output=True,
    )
    if units.returncode != 0:
        print("未找到 systemd 的 docker.service，请手动重启 docker 使配置生效")
        return
    result = subprocess.run(
        ["systemctl", "restart", "docker"],
        capture_output=True,
    )
    if result.returncode != 0:
        print("docker.service 重启失败，请手动执行: sudo systemctl restart docker", file=sys.stderr)
        return
    print("已重启 docker.service")
    time.sleep(1)
    subprocess.run(
        ["docker", "info", "--format", "生效的 registry mirrors: {{json .RegistryConfig.Mirrors}}"],
        check=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="一键配置 Docker registry 镜像加速")
    parser.add_argument("--dry-run", action="store_true", help="只打印最终配置，不改任何文件")
    parser.add_argument(
        "--dst",
        type=Path,
        default=Path(os.environ.get("DST", "/etc/docker/daemon.json")),
        help="目标路径（默认 /etc/docker/daemon.json）",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="指定 docker 数据目录（如 /mnt/data1/docker）；"
        "已有 data-root 默认保留，不会被覆盖",
    )
    parser.add_argument(
        "--overwrite-data-root",
        action="store_true",
        help="允许 --data-root 覆盖已有的 data-root（注意：旧目录中的镜像不会自动迁移）",
    )
    args = parser.parse_args()

    merged = merge(SRC, args.dst)

    if args.data_root is not None:
        data_root = str(args.data_root.expanduser())
        if not os.path.isabs(data_root):
            sys.exit(f"ERROR: --data-root 需要绝对路径，收到: {args.data_root}")
        existing = merged.get("data-root")
        if existing and existing != data_root and not args.overwrite_data_root:
            print(
                f"保留已有 data-root: {existing}\n"
                f"（--data-root {data_root} 未生效；确认要覆盖请加 --overwrite-data-root，"
                "注意旧目录中的镜像不会自动迁移）"
            )
        else:
            merged["data-root"] = data_root

    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"

    if args.dry_run:
        print(f"== 将写入 {args.dst} 的最终配置 ==")
        print(text, end="")
        return

    if not os.access(args.dst.parent if args.dst.parent.exists() else args.dst.parent.parent, os.W_OK):
        sys.exit(f"没有权限写入 {args.dst}，请使用 sudo 运行")

    args.dst.parent.mkdir(parents=True, exist_ok=True)
    if args.dst.exists():
        backup = args.dst.with_suffix(f".json.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(args.dst, backup)
        print(f"已备份原配置到 {backup}")

    # 原子写入，避免写到一半损坏 daemon 配置
    fd, tmp = tempfile.mkstemp(dir=args.dst.parent, prefix=".daemon.json.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, args.dst)
    print(f"已写入 {args.dst}")

    restart_docker()


if __name__ == "__main__":
    main()
