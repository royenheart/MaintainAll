"""卸载 Clash Verge Rev，以及残留的便携 mihomo。

  python deploy/app-proxy-manage/uninstall.py
  python deploy/app-proxy-manage/uninstall.py --client verge
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

if os.name != "nt":
    print("当前卸载脚本只支持 Windows", file=sys.stderr)
    raise SystemExit(1)

from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from install import (  # noqa: E402
    MIHOMO_WINGET_ID,
    STATE_DIR,
    VERGE_WINGET_ID,
    set_tray_autostart,
    stop_verge,
    winget_uninstall,
)


def main() -> None:
    p = argparse.ArgumentParser(description="卸载 Clash Verge Rev / 便携 mihomo")
    p.add_argument(
        "--client",
        choices=("all", "verge", "mihomo"),
        default="all",
        help="all=Verge+残留 mihomo+向导状态；verge/mihomo 只卸对应客户端",
    )
    p.add_argument("--keep-data", action="store_true", help="保留 %%LOCALAPPDATA%%\\MaintainAll\\app-proxy")
    args = p.parse_args()

    stop_verge()
    set_tray_autostart(False)

    if args.client in ("all", "verge"):
        winget_uninstall(VERGE_WINGET_ID)

    if args.client in ("all", "mihomo"):
        winget_uninstall(MIHOMO_WINGET_ID)
        leftover = STATE_DIR / "mihomo.exe"
        if leftover.is_file():
            leftover.unlink()
            print(f"删除 {leftover}")

    if args.client == "all" and not args.keep_data and STATE_DIR.is_dir():
        print(f"删除 {STATE_DIR}")
        shutil.rmtree(STATE_DIR, ignore_errors=True)

    print("卸载完成。")


if __name__ == "__main__":
    main()
