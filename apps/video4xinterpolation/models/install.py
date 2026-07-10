#!/usr/bin/env python3

# RIFE: https://github.com/hzwer/Practical-RIFE
# 4.26 - 2024.09.21

"""下载 RIFE 模型并解压至 models/RIFEv4.26_0921/"""

import urllib.request
import zipfile
from pathlib import Path

URL = "https://drive.google.com/uc?export=download&id=1gViYvvQrtETBgU1w8axZSsr7YUuw31uy"
HERE = Path(__file__).resolve().parent
ZIP_PATH = HERE / "RIFEv4.26_0921.zip"
DEST = HERE / "RIFEv4.26_0921"


def main() -> None:
    if not ZIP_PATH.exists():
        print(f"下载模型 -> {ZIP_PATH}")
        urllib.request.urlretrieve(URL, ZIP_PATH)
    else:
        print(f"已存在压缩包，跳过下载: {ZIP_PATH}")

    print(f"解压 -> {DEST}")
    DEST.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH) as z:
        for name in z.namelist():
            if name.startswith("__MACOSX/"):
                continue
            z.extract(name, DEST)

    print("完成")


if __name__ == "__main__":
    main()
