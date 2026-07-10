"""Fixed-resolution tiers for VitisAI-friendly ONNX (no dynamic H/W)."""

from __future__ import annotations

from pathlib import Path

# Default shipped tiers (H, W) after RIFE 32-align pad.
# 720x1280 → 736x1280; 1080x1920 → 1088x1920.
DEFAULT_FIXED_SIZES: tuple[tuple[int, int], ...] = (
    (736, 1280),
    (1088, 1920),
)


def size_tag(height: int, width: int) -> str:
    return f"{height}x{width}"


def parse_size(text: str) -> tuple[int, int]:
    """Parse '1088x1920' or '1088X1920' → (1088, 1920)."""
    t = text.strip().lower().replace("*", "x").replace(",", "x")
    if "x" not in t:
        raise ValueError(f"expected HxW like 1088x1920, got {text!r}")
    a, b = t.split("x", 1)
    return int(a), int(b)


def parse_size_list(text: str) -> list[tuple[int, int]]:
    """Parse '736x1280,1088x1920'."""
    parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
    if not parts:
        return list(DEFAULT_FIXED_SIZES)
    return [parse_size(p) for p in parts]


def fixed_model_dir(onnx_root: Path, height: int, width: int) -> Path:
    return Path(onnx_root) / "fixed" / size_tag(height, width)


def fixed_onnx_paths(onnx_root: Path, height: int, width: int) -> dict[str, Path]:
    d = fixed_model_dir(onnx_root, height, width)
    return {
        "stage_a": d / "rife_stage_encode_block01.onnx",
        "stage_b": d / "rife_stage_block234.onnx",
        "stage_b_quant": d / "rife_stage_block234_quant.onnx",
        "full": d / "rife_full.onnx",
    }


def match_fixed_size(
    height: int,
    width: int,
    sizes: tuple[tuple[int, int], ...] | list[tuple[int, int]] = DEFAULT_FIXED_SIZES,
) -> tuple[int, int]:
    """Exact match against a known fixed tier (use padded H/W)."""
    key = (int(height), int(width))
    for h, w in sizes:
        if (h, w) == key:
            return h, w
    avail = ", ".join(size_tag(h, w) for h, w in sizes)
    raise ValueError(
        f"No fixed-tier model for {size_tag(height, width)}. "
        f"Available: {avail}. "
        f"Re-export/quantize that size, or pad input to a supported tier."
    )


def resolve_onnx_paths_for_hw(
    onnx_root: Path,
    height: int,
    width: int,
    *,
    prefer_fixed: bool = True,
    sizes: tuple[tuple[int, int], ...] = DEFAULT_FIXED_SIZES,
) -> tuple[dict[str, Path], tuple[int, int], str]:
    """Pick ONNX paths for padded (height, width).

    Returns (paths, (h, w), kind) where kind is ``fixed`` or ``dynamic``.
    """
    from rife_amd.runtime.paths import default_onnx_paths

    onnx_root = Path(onnx_root)
    if prefer_fixed:
        try:
            fh, fw = match_fixed_size(height, width, sizes)
        except ValueError:
            fh = fw = -1
        if fh > 0:
            paths = fixed_onnx_paths(onnx_root, fh, fw)
            if paths["stage_a"].is_file() and paths["stage_b"].is_file():
                return paths, (fh, fw), "fixed"
    # Legacy dynamic graphs under onnx_root (tests / CPU fallback)
    dyn = default_onnx_paths(onnx_root)
    if dyn["stage_a"].is_file() and dyn["stage_b"].is_file():
        return dyn, (height, width), "dynamic"
    raise FileNotFoundError(
        f"No ONNX for {size_tag(height, width)} under {onnx_root}. "
        f"Run: python scripts/export_onnx.py --fixed-tiers && "
        f"python scripts/quantize_rife.py --sizes {size_tag(height, width)}"
    )
