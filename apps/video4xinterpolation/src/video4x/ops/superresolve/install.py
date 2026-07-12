"""Download Real-ESRGAN official weights into models/realesrgan/."""

from __future__ import annotations

import urllib.request
from pathlib import Path

from video4x.ops.superresolve.model import MODEL_PRESETS, resolve_model_name

HERE = Path(__file__).resolve().parents[4] / "models" / "realesrgan"


def weights_dir() -> Path:
    HERE.mkdir(parents=True, exist_ok=True)
    return HERE


def weight_path(model_name: str) -> Path:
    key = resolve_model_name(model_name)
    return weights_dir() / MODEL_PRESETS[key]["file"]


def download_model(model_name: str, *, force: bool = False) -> Path:
    key = resolve_model_name(model_name)
    meta = MODEL_PRESETS[key]
    dest = weights_dir() / meta["file"]
    if dest.exists() and not force:
        return dest
    print(f"Downloading {meta['file']} -> {dest}")
    urllib.request.urlretrieve(meta["url"], dest)
    return dest


def download_all(*, force: bool = False) -> list[Path]:
    return [download_model(k, force=force) for k in MODEL_PRESETS]


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Download Real-ESRGAN weights")
    p.add_argument(
        "--models",
        default="x2plus,x4plus,x4plus_anime",
        help="Comma-separated model keys",
    )
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    for name in [x.strip() for x in args.models.split(",") if x.strip()]:
        path = download_model(name, force=args.force)
        print(f"OK {name}: {path}")


if __name__ == "__main__":
    main()
