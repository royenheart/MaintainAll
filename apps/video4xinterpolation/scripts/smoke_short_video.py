"""Short-clip smoke test for RIFE dual-stream / split-pipeline (first N frames).

Examples:
  python scripts/smoke_short_video.py -i path/to.mp4 -o tmp/smoke.mp4
  python scripts/smoke_short_video.py -i in.mp4 --max-frames 36 --backend dual-stream --memory shared
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Avoid scripts/video4x.py shadowing the installed/src package.
_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SCRIPTS) in sys.path:
    sys.path.remove(str(_SCRIPTS))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import numpy as np

from video4x.inference.config import InferenceConfig
from video4x.inference.engine import RifeInferenceEngine
from video4x.inference.progress import StdoutProgressReporter
from video4x.runtime.memory import create_memory_planner
from video4x.runtime.platform import detect_platform
from video4x.runtime.preprocess import crop_hw
from video4x.runtime.resolutions import DEFAULT_FIXED_SIZES, parse_size, size_tag
from video4x.runtime.video_io import detect_video_fps, read_frames, write_video


def _pick_fixed_tier(h: int, w: int, prefer: str | None) -> tuple[int, int]:
    """Pick a fixed tier that can contain (h,w); prefer exact / smallest area."""
    if prefer:
        return parse_size(prefer)
    candidates = [(th, tw) for th, tw in DEFAULT_FIXED_SIZES if th >= h and tw >= w]
    if not candidates:
        # fall back to largest tier (caller may still fail if too small)
        return max(DEFAULT_FIXED_SIZES, key=lambda hw: hw[0] * hw[1])
    return min(candidates, key=lambda hw: hw[0] * hw[1])


def _pad_to_hw(fr: np.ndarray, th: int, tw: int) -> np.ndarray:
    """Edge-pad NCHW frame to exactly (th, tw)."""
    if fr.ndim != 4 or fr.shape[0] != 1:
        raise ValueError(f"expected NCHW batch=1, got {fr.shape}")
    _, _, h, w = fr.shape
    if h > th or w > tw:
        raise ValueError(f"frame {h}x{w} does not fit target {th}x{tw}")
    ph, pw = th - h, tw - w
    if ph or pw:
        fr = np.pad(fr, ((0, 0), (0, 0), (0, ph), (0, pw)), mode="edge")
    return np.ascontiguousarray(fr, dtype=np.float32)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="RIFE short-video smoke (max_frames)")
    p.add_argument("-i", "--input", type=Path, required=True)
    p.add_argument("-o", "--output", type=Path, default=Path("tmp/smoke_dual_iobind.mp4"))
    p.add_argument("--max-frames", type=int, default=36)
    p.add_argument("--backend", default="dual-stream")
    p.add_argument(
        "--memory",
        default="shared",
        choices=["auto", "host", "pinned", "shared"],
    )
    p.add_argument("--onnx-dir", type=Path, default=Path("models/onnx"))
    p.add_argument("--platform", default="auto")
    p.add_argument("--fp16", action="store_true")
    p.add_argument(
        "--fixed-tier",
        default="auto",
        help="HxW fixed ONNX tier (e.g. 736x1280) or auto = smallest containing tier",
    )
    p.add_argument(
        "--use-iobinding",
        default="auto",
        choices=["auto", "on", "off"],
        help="auto: follow memory=shared; on/off force",
    )
    p.add_argument("--no-progress", action="store_true")
    args = p.parse_args(argv)

    use_iob: bool | None
    if args.use_iobinding == "auto":
        use_iob = None
    elif args.use_iobinding == "on":
        use_iob = True
    else:
        use_iob = False

    cfg = InferenceConfig(
        mode=args.backend,
        onnx_dir=args.onnx_dir,
        fp16=args.fp16,
        platform=args.platform,
        memory_mode=args.memory,
        use_iobinding=use_iob,
    )
    mem = create_memory_planner(cfg.platform)
    resolved = mem.resolve_mode(cfg.memory_mode)
    prof = mem.profile()
    mem.close()

    print(
        f"platform={cfg.platform} (detected={detect_platform().value}) "
        f"backend={cfg.mode} memory={resolved.value} "
        f"use_iobinding={cfg.use_iobinding!r} "
        f"(ram={prof.system_ram_mb:.0f}MB shared={prof.gpu_shared_mb} apu={prof.unified_apu})"
    )

    t0 = time.perf_counter()
    frames = list(read_frames(args.input, max_frames=args.max_frames))
    decode_s = time.perf_counter() - t0
    if not frames:
        raise SystemExit(f"No frames decoded from {args.input}")
    _, _, h, w = frames[0].shape
    src_fps = detect_video_fps(args.input)
    out_fps = src_fps * 2.0
    prefer = None if args.fixed_tier == "auto" else args.fixed_tier
    th, tw = _pick_fixed_tier(h, w, prefer)
    print(
        f"decoded {len(frames)} frames in {decode_s:.2f}s "
        f"({w}x{h} → pad {size_tag(th, tw)} for fixed ONNX; "
        f"src={src_fps:.3g}fps → out={out_fps:.3g}fps)"
    )
    padded = [_pad_to_hw(fr, th, tw) for fr in frames]

    on_progress = None if args.no_progress else StdoutProgressReporter()
    t1 = time.perf_counter()
    with RifeInferenceEngine(cfg, on_progress=on_progress) as engine:
        out_padded = engine.interpolate_frames(padded)
        st = engine.stats()
        model_kind = getattr(engine, "_model_kind", None)
        mode = engine.mode
        sessions = getattr(getattr(engine, "_backend", None), "_sessions", None)
        iob_used = bool(getattr(sessions, "use_iobinding", False)) if sessions else False
        iob_detail = getattr(sessions, "iobinding_detail", "") if sessions else ""
        out_frames = [crop_hw(fr, h, w) for fr in out_padded]
        write_video(
            args.output,
            (f[0] if f.ndim == 4 else f for f in out_frames),
            fps=out_fps,
            width=w,
            height=h,
        )
    elapsed = time.perf_counter() - t1

    summary = {
        "ok": True,
        "input": str(args.input),
        "output": str(args.output.resolve()),
        "max_frames": args.max_frames,
        "decoded_frames": len(frames),
        "output_frames": len(out_frames),
        "native_hw": [h, w],
        "fixed_tier": size_tag(th, tw),
        "backend": mode,
        "model_kind": model_kind,
        "providers": dict(st.providers),
        "gpu_hits": st.gpu_hits,
        "npu_hits": st.npu_hits,
        "fallback_reason": st.fallback_reason,
        "memory_mode": st.memory_mode,
        "memory_detail": st.memory_detail,
        "use_iobinding": getattr(st, "use_iobinding", iob_used),
        "iobinding_detail": iob_detail,
        "total_calls": st.total_calls,
        "total_ms": round(st.total_ms, 1),
        "stage_a_ms": round(st.stage_a_ms, 1),
        "stage_b_ms": round(st.stage_b_ms, 1),
        "wall_s": round(elapsed, 2),
        "src_fps": src_fps,
        "out_fps": out_fps,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Wrote {args.output} ({args.output.stat().st_size} bytes) in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())