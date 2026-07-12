"""Video interpolation CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from video4x.inference.comparator import InferenceComparator
from video4x.inference.config import InferenceConfig
from video4x.inference.engine import RifeInferenceEngine
from video4x.inference.progress import StdoutProgressReporter
from video4x.runtime.backends.registry import list_backends
from video4x.runtime.platform import detect_platform
from video4x.runtime.video_io import read_frames


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="RIFE video interpolation")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--backend", default="split-pipeline")
    parser.add_argument("--backends", default="", help="Comma list for compare mode")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--onnx-dir", type=Path, default=Path("models/onnx"))
    parser.add_argument(
        "--platform",
        default="auto",
        choices=["auto", "windows", "wsl", "linux"],
        help="EP defaults: windows=dml+vitisai, wsl/linux=rocm+vitisai (default: auto-detect)",
    )
    parser.add_argument(
        "--ep-preference",
        default="",
        help="Comma list override, e.g. dml,vitisai,cpu or rocm,cpu",
    )
    parser.add_argument(
        "--memory",
        default="auto",
        choices=["auto", "host", "pinned", "shared"],
        help="Host buffer mode: auto detects APU shared pool → pinned/shared; host=pageable",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable stderr progress lines (decode/init/interpolate/encode)",
    )
    args = parser.parse_args(argv)

    ep = [x.strip() for x in args.ep_preference.split(",") if x.strip()]
    cfg = InferenceConfig(
        mode=args.backend,
        onnx_dir=args.onnx_dir,
        fp16=args.fp16,
        platform=args.platform,
        ep_preference=ep,
        memory_mode=args.memory,
    )
    from video4x.runtime.memory import create_memory_planner

    mem = create_memory_planner(cfg.platform)
    resolved = mem.resolve_mode(cfg.memory_mode)
    prof = mem.profile()
    mem.close()
    print(
        f"platform={cfg.platform} (detected={detect_platform().value}) "
        f"ep={cfg.ep_preference} memory={resolved.value} "
        f"(ram={prof.system_ram_mb:.0f}MB shared={prof.gpu_shared_mb} apu={prof.unified_apu})"
    )

    if args.compare:
        frames = list(read_frames(args.input, max_frames=5))
        names = [b.strip() for b in args.backends.split(",") if b.strip()] or list_backends()
        comp = InferenceComparator(cfg)
        results = comp.compare_on_frames(frames, modes=names)
        comp.print_table(results)
        return

    on_progress = None if args.no_progress else StdoutProgressReporter()
    with RifeInferenceEngine(cfg, on_progress=on_progress) as engine:
        result = engine.interpolate_video(args.input, args.output)
    print(f"Done: {result.output_frames} frames via {result.mode}")
    print(result.stats)


if __name__ == "__main__":
    main()
