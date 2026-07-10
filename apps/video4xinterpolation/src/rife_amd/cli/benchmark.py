"""Backend benchmark CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from rife_amd.inference.comparator import InferenceComparator
from rife_amd.inference.config import InferenceConfig
from rife_amd.runtime.platform import detect_platform


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Benchmark RIFE backends")
    parser.add_argument("--backends", default="cpu-baseline,single-ep,split-pipeline")
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--onnx-dir", type=Path, default=Path("models/onnx"))
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument(
        "--platform",
        default="auto",
        choices=["auto", "windows", "wsl", "linux"],
    )
    parser.add_argument("--ep-preference", default="")
    parser.add_argument(
        "--memory",
        default="auto",
        choices=["auto", "host", "pinned", "shared"],
    )
    args = parser.parse_args(argv)

    ep = [x.strip() for x in args.ep_preference.split(",") if x.strip()]
    cfg = InferenceConfig(
        onnx_dir=args.onnx_dir,
        fp16=args.fp16,
        platform=args.platform,
        ep_preference=ep,
        memory_mode=args.memory,
    )
    print(f"platform={cfg.platform} (detected={detect_platform().value}) ep={cfg.ep_preference} memory={cfg.memory_mode}")
    shape = (1, 3, args.height, args.width)
    names = [n.strip() for n in args.backends.split(",") if n.strip()]

    comp = InferenceComparator(cfg)
    results = comp.benchmark(modes=names, shape=shape, iterations=args.iterations)
    comp.print_table(results)


if __name__ == "__main__":
    main()
