#!/usr/bin/env python3
"""Encode a product-demo video or frame sequence to a small, readable GIF.

The encoder always creates a palette in a first pass, then applies it in a
second pass. That avoids the banding and shimmer that comes from using ffmpeg's
default GIF encoder on UI footage.

Examples:
  python encode_demo_gif.py demo.webm demo.gif --fps 12 --width 900
  python encode_demo_gif.py frames/f%04d.png demo.gif --framerate 30 --trim-start 0.8
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise ValueError("value must be positive")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="Video file or image-sequence pattern (for example frames/f%04d.png).")
    parser.add_argument("output", type=Path, help="Destination .gif.")
    parser.add_argument("--fps", type=positive, default=12, help="Output GIF frames per second (default: 12).")
    parser.add_argument("--width", type=positive, default=900, help="Output width in pixels; height follows aspect ratio (default: 900).")
    parser.add_argument("--colors", type=positive, default=160, help="Palette size, 2-256 (default: 160).")
    parser.add_argument("--trim-start", type=float, default=0.0, help="Start offset in seconds for video input (default: 0).")
    parser.add_argument("--trim-end", type=float, default=0.0, help="Optional end offset in seconds for video input (default: 0).")
    parser.add_argument("--framerate", type=positive, default=30, help="Input rate for an image sequence (default: 30).")
    parser.add_argument("--dither", choices=("bayer", "none"), default="bayer", help="Palette dither mode (default: bayer).")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output file.")
    args = parser.parse_args()

    if args.colors > 256:
        parser.error("--colors must be at most 256")
    if args.output.suffix.lower() != ".gif":
        parser.error("--output must end in .gif")
    if args.output.exists() and not args.overwrite:
        parser.error(f"refusing to overwrite {args.output}; pass --overwrite")
    if not shutil.which("ffmpeg"):
        parser.error("ffmpeg not found on PATH")

    source = str(args.source)
    is_sequence = "%" in source
    input_args = ["-framerate", str(args.framerate)] if is_sequence else []
    if not is_sequence and args.trim_start:
        input_args.extend(["-ss", str(args.trim_start)])
    if not is_sequence and args.trim_end:
        input_args.extend(["-to", str(args.trim_end)])
    filter_graph = (
        f"fps={args.fps},scale={args.width}:-1:flags=lanczos,"
        "split[s0][s1];[s0]palettegen=max_colors=" + str(args.colors) + "[p];"
        "[s1][p]paletteuse=" + ("dither=bayer:bayer_scale=2" if args.dither == "bayer" else "dither=none")
    )
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y" if args.overwrite else "-n",
               *input_args, "-i", source, "-vf", filter_graph, "-loop", "0", str(args.output)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(json.dumps({"passed": False, "command": command, "stderr": result.stderr}, indent=2))
        return 1
    print(json.dumps({
        "passed": True,
        "output": str(args.output),
        "bytes": args.output.stat().st_size,
        "fps": args.fps,
        "width": args.width,
        "colors": args.colors,
        "command": command,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
