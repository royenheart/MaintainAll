"""Download Practical-RIFE v4.26 weights into models/RIFEv4.26_0921/."""

from __future__ import annotations

import zipfile
from pathlib import Path
from urllib.request import urlretrieve

# Practical-RIFE 4.26 (2024.09.21)
RIFE_URL = "https://drive.google.com/uc?export=download&id=1gViYvvQrtETBgU1w8axZSsr7YUuw31uy"
RIFE_ZIP_NAME = "RIFEv4.26_0921.zip"
RIFE_DIR_NAME = "RIFEv4.26_0921"


def models_root() -> Path:
    """Project models/ directory (src/video4x/ops/interpolate → …/models)."""
    # install.py → interpolate → ops → video4x → src → project
    return Path(__file__).resolve().parents[4] / "models"


def rife_zip_path() -> Path:
    return models_root() / RIFE_ZIP_NAME


def rife_dest_dir() -> Path:
    return models_root() / RIFE_DIR_NAME


def rife_pkl_path() -> Path:
    return rife_dest_dir() / "train_log" / "flownet.pkl"


def download_rife(*, force: bool = False) -> Path:
    """
    Download + extract RIFE v4.26 weights.

    Returns path to flownet.pkl (or dest dir if pkl layout differs).
    """
    root = models_root()
    root.mkdir(parents=True, exist_ok=True)
    zip_path = rife_zip_path()
    dest = rife_dest_dir()

    if force and zip_path.exists():
        zip_path.unlink()

    if not zip_path.exists():
        print(f"Downloading RIFE -> {zip_path}")
        urlretrieve(RIFE_URL, zip_path)
    else:
        print(f"RIFE zip exists, skip download: {zip_path}")

    need_extract = force or not rife_pkl_path().is_file()
    if need_extract:
        print(f"Extracting -> {dest}")
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                if name.startswith("__MACOSX/"):
                    continue
                z.extract(name, dest)
    else:
        print(f"RIFE weights present, skip extract: {rife_pkl_path()}")

    pkl = rife_pkl_path()
    if pkl.is_file():
        return pkl
    return dest


def main() -> None:
    path = download_rife()
    print(f"OK rife: {path}")


if __name__ == "__main__":
    main()
