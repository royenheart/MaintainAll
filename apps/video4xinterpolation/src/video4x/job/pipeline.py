"""EnhanceJob + ordered multi-operator pipeline."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from video4x.inference.progress import ProgressCallback, ProgressEvent
from video4x.ops.base import OpSpec, OperatorStats
from video4x.ops.interpolate import InterpolateOperator
from video4x.ops.superresolve import SuperResolveConfig, SuperResolveEngine
from video4x.ops.superresolve.export import default_onnx_root


ProgressFn = ProgressCallback


@dataclass
class EnhanceJobConfig:
    input_path: Path
    output_path: Path
    # Ordered operator ids, e.g. ["interpolate", "superresolve"]
    order: list[str] = field(default_factory=lambda: ["interpolate"])
    interpolate: OpSpec | None = None
    superresolve: OpSpec | None = None
    # None = auto-detect from input video (interpolate uses src*2)
    fps: float | None = None
    keep_temp: bool = False


@dataclass
class EnhanceResult:
    output_path: Path
    steps: list[dict[str, Any]] = field(default_factory=list)
    stats: list[OperatorStats] = field(default_factory=list)


def _default_interp_spec() -> OpSpec:
    return OpSpec(op="interpolate", backend="split-pipeline", platform="auto")


def _default_sr_spec() -> OpSpec:
    return OpSpec(op="superresolve", model="x4plus", backend="split-pipeline", platform="auto")


class EnhancePipeline:
    """Run operators in user-specified order via temp intermediates when chaining."""

    def __init__(self, on_progress: ProgressFn | None = None) -> None:
        self._on_progress = on_progress

    def run(self, cfg: EnhanceJobConfig) -> EnhanceResult:
        order = [o.strip().lower() for o in cfg.order if o.strip()]
        if not order:
            raise ValueError("order must include at least one of: interpolate, superresolve")
        for name in order:
            if name not in ("interpolate", "superresolve"):
                raise ValueError(f"Unknown op '{name}'")

        inp = Path(cfg.input_path)
        final = Path(cfg.output_path)
        if not inp.is_file():
            raise FileNotFoundError(inp)

        from video4x.runtime.video_io import detect_video_fps

        # Track working fps through the pipeline (auto from source unless overridden)
        working_fps = float(cfg.fps) if cfg.fps is not None else detect_video_fps(inp)

        steps: list[dict[str, Any]] = []
        stats: list[OperatorStats] = []
        current = inp
        temps: list[Path] = []

        try:
            for i, name in enumerate(order):
                is_last = i == len(order) - 1
                if is_last:
                    out = final
                else:
                    tmp = Path(tempfile.mkstemp(prefix=f"video4x_{name}_", suffix=".mp4")[1])
                    temps.append(tmp)
                    out = tmp

                if self._on_progress:
                    self._on_progress(
                        ProgressEvent(
                            phase="pipeline",
                            message=f"step {i + 1}/{len(order)}: {name}",
                            current=i,
                            total=len(order),
                        )
                    )

                if name == "interpolate":
                    spec = cfg.interpolate or _default_interp_spec()
                    op = InterpolateOperator(
                        backend=spec.backend,
                        platform=spec.platform,
                        fp16=spec.fp16,
                        memory_mode=spec.memory_mode,
                        onnx_dir=spec.onnx_dir,
                        on_progress=self._on_progress,
                    )
                    try:
                        op.init()
                        # RIFE 2× frames; engine writes at src_fps*2 when fps passed as source rate
                        result = op.process_video(current, out, fps=working_fps)
                        steps.append({"op": name, "result": result, "output": str(out)})
                        stats.append(op.stats())
                        working_fps = working_fps * 2.0
                    finally:
                        op.close()
                else:
                    spec = cfg.superresolve or _default_sr_spec()
                    scfg = SuperResolveConfig(
                        model=spec.model or "x4plus",
                        backend=spec.backend,
                        platform=spec.platform,
                        fp16=spec.fp16,
                        memory_mode=spec.memory_mode,
                        onnx_dir=spec.onnx_dir or default_onnx_root(),
                        tile=spec.tile,
                        tile_pad=spec.tile_pad,
                    )
                    eng = SuperResolveEngine(scfg, on_progress=self._on_progress)
                    try:
                        result = eng.enhance_video(current, out, fps=working_fps)
                        steps.append({"op": name, "result": result, "output": str(out)})
                        stats.append(eng.stats())
                    finally:
                        eng.close()

                current = out

            if self._on_progress:
                self._on_progress(
                    ProgressEvent(
                        phase="done",
                        message=f"wrote {final}",
                        current=len(order),
                        total=len(order),
                    )
                )
            return EnhanceResult(output_path=final, steps=steps, stats=stats)
        finally:
            if not cfg.keep_temp:
                for t in temps:
                    try:
                        t.unlink(missing_ok=True)
                    except OSError:
                        pass


class EnhanceJob:
    """Facade used by CLI / TUI."""

    def __init__(self, config: EnhanceJobConfig, on_progress: ProgressFn | None = None) -> None:
        self.config = config
        self._on_progress = on_progress

    def run(self) -> EnhanceResult:
        return EnhancePipeline(on_progress=self._on_progress).run(self.config)


def parse_order(ops: str | Sequence[str], order: str | Sequence[str] | None = None) -> list[str]:
    """
    Build execution order.

    - ops: enabled ops (comma list or sequence)
    - order: optional explicit order; must be a permutation of enabled ops
    """
    if isinstance(ops, str):
        enabled = [x.strip().lower() for x in ops.split(",") if x.strip()]
    else:
        enabled = [str(x).strip().lower() for x in ops if str(x).strip()]
    if not enabled:
        raise ValueError("no operators selected")
    if order is None or order == "" or order == ():
        return enabled
    if isinstance(order, str):
        seq = [x.strip().lower() for x in order.split(",") if x.strip()]
    else:
        seq = [str(x).strip().lower() for x in order if str(x).strip()]
    if sorted(seq) != sorted(enabled):
        raise ValueError(f"order {seq} must match enabled ops {enabled}")
    return seq
