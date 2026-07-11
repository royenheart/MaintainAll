"""Unified video4x CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from video4x.job import EnhanceJob, EnhanceJobConfig, parse_order
from video4x.ops.base import OpSpec
from video4x.ops.superresolve.export import default_onnx_root
from video4x.ops.superresolve.model import MODEL_PRESETS
from video4x.inference.progress import StdoutProgressReporter


def _cmd_run(args: argparse.Namespace) -> int:
    order = parse_order(args.ops, args.order)
    interp = None
    sr = None
    if "interpolate" in order:
        interp = OpSpec(
            op="interpolate",
            backend=args.fi_backend,
            platform=args.platform,
            fp16=args.fp16,
            memory_mode=args.memory,
            onnx_dir=Path(args.fi_onnx_dir) if args.fi_onnx_dir else None,
        )
    if "superresolve" in order:
        sr = OpSpec(
            op="superresolve",
            model=args.sr_model,
            backend=args.sr_backend,
            platform=args.platform,
            fp16=args.fp16,
            memory_mode=args.memory,
            onnx_dir=Path(args.sr_onnx_dir) if args.sr_onnx_dir else default_onnx_root(),
            tile=args.tile,
            tile_pad=args.tile_pad,
        )
    cfg = EnhanceJobConfig(
        input_path=Path(args.input),
        output_path=Path(args.output),
        order=order,
        interpolate=interp,
        superresolve=sr,
        keep_temp=args.keep_temp,
    )
    progress = None if args.no_progress else StdoutProgressReporter()
    result = EnhanceJob(cfg, on_progress=progress).run()
    print(f"Wrote {result.output_path}")
    for i, st in enumerate(result.stats):
        print(
            f"  step[{i}] {st.name}: calls={st.total_calls} ms={st.total_ms:.0f} "
            f"gpu={st.gpu_hits} npu={st.npu_hits} ep={st.providers}"
        )
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    target = args.target
    if target == "realesrgan":
        from video4x.ops.superresolve.export import main as export_sr

        argv = ["--models", args.models]
        if args.out_dir:
            argv.extend(["--out-dir", str(args.out_dir)])
        if args.no_download:
            argv.append("--no-download")
        export_sr(argv)
        return 0
    if target == "rife":
        from video4x.onnx_export import main as export_rife

        # Prefer explicit rife_args (after optional "--")
        extra = [a for a in (args.rife_args or []) if a != "--"]
        export_rife(extra or None)
        return 0
    raise SystemExit(f"Unknown export target: {target}")


def _cmd_tui(_args: argparse.Namespace) -> int:
    from video4x.tui.app import run_tui

    run_tui()
    return 0


def _cmd_download(args: argparse.Namespace) -> int:
    from video4x.ops.interpolate.install import download_rife
    from video4x.ops.superresolve.install import download_model
    from video4x.ops.superresolve.model import MODEL_PRESETS

    names = [x.strip() for x in args.models.split(",") if x.strip()]
    if not names:
        names = ["rife", *MODEL_PRESETS.keys()]

    rife_aliases = {"rife", "rife426", "rifev4.26", "practical-rife"}
    for name in names:
        key = name.lower().replace(" ", "")
        if key in rife_aliases:
            path = download_rife(force=args.force)
            print(f"OK rife: {path}")
        else:
            path = download_model(name, force=args.force)
            print(f"OK {name}: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="video4x",
        description="Video4x — AMD GPU+NPU video enhance (interpolate + Real-ESRGAN)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run enhance pipeline")
    run.add_argument("-i", "--input", required=True)
    run.add_argument("-o", "--output", required=True)
    run.add_argument(
        "--ops",
        default="interpolate",
        help="Enabled ops, comma-separated: interpolate,superresolve",
    )
    run.add_argument(
        "--order",
        default=None,
        help="Execution order (permutation of --ops). Default = --ops order",
    )
    run.add_argument("--platform", default="auto")
    run.add_argument("--fp16", action="store_true")
    run.add_argument("--memory", default="auto", choices=["auto", "host", "pinned", "shared"])
    run.add_argument("--no-progress", action="store_true")
    run.add_argument("--keep-temp", action="store_true")
    run.add_argument("--fi-backend", default="split-pipeline")
    run.add_argument("--fi-onnx-dir", default=None)
    run.add_argument("--sr-model", default="x4plus", choices=list(MODEL_PRESETS.keys()))
    run.add_argument("--sr-backend", default="split-pipeline")
    run.add_argument("--sr-onnx-dir", default=None)
    run.add_argument("--tile", type=int, default=0, help="0=auto")
    run.add_argument("--tile-pad", type=int, default=10)
    run.set_defaults(func=_cmd_run)

    exp = sub.add_parser(
        "export",
        help=(
            "Convert PyTorch weights → ONNX for ORT inference. "
            "Supports: rife (v4.26); realesrgan (x2plus,x4plus,x4plus_anime)"
        ),
    )
    exp.add_argument("target", choices=["realesrgan", "rife"])
    exp.add_argument("--models", default="x2plus,x4plus,x4plus_anime")
    exp.add_argument("--out-dir", type=Path, default=None)
    exp.add_argument("--no-download", action="store_true")
    exp.add_argument(
        "rife_args",
        nargs=argparse.REMAINDER,
        help="Extra args for RIFE export, e.g. --fixed-tiers  (use: video4x export rife -- --fixed-tiers)",
    )
    exp.set_defaults(func=_cmd_export)

    dl = sub.add_parser(
        "download",
        help="Download model weights (RIFE + Real-ESRGAN)",
    )
    dl.add_argument(
        "--models",
        default="rife,x2plus,x4plus,x4plus_anime",
        help="Comma list: rife and/or Real-ESRGAN keys (x2plus,x4plus,x4plus_anime)",
    )
    dl.add_argument("--force", action="store_true", help="Re-download even if present")
    dl.set_defaults(func=_cmd_download)

    tui = sub.add_parser("tui", help="Launch Textual TUI")
    tui.set_defaults(func=_cmd_tui)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Strip leading "--" from REMAINDER (video4x export rife -- --fixed-tiers)
    if getattr(args, "rife_args", None):
        args.rife_args = [a for a in args.rife_args if a != "--"]
        while args.rife_args and args.rife_args[0] == "--":
            args.rife_args = args.rife_args[1:]
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
