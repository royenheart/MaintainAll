"""Compare inference modes side-by-side."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field, replace
from typing import Iterable

import numpy as np

from rife_amd.inference.config import InferenceConfig, InferenceMode
from rife_amd.inference.engine import RifeInferenceEngine
from rife_amd.runtime.backends.registry import list_backends
from rife_amd.runtime.video_io import frame_pairs


@dataclass
class CompareResult:
    mode: str
    elapsed_ms: float | None = None
    mean_ms: float | None = None
    p95_ms: float | None = None
    fps: float | None = None
    device_hint: str | None = None
    npu_hits: int = 0
    gpu_hits: int = 0
    fallback_reason: str | None = None
    error: str | None = None
    stats: dict = field(default_factory=dict)


class InferenceComparator:
    """
    Run the same workload across multiple inference modes.

    Each comparison creates a fresh engine per mode so results are independent.
    """

    def __init__(self, base_config: InferenceConfig | None = None) -> None:
        self._base_config = base_config or InferenceConfig()

    def compare_on_frames(
        self,
        frames: list[np.ndarray],
        modes: Iterable[str | InferenceMode] | None = None,
        max_pairs: int = 3,
    ) -> list[CompareResult]:
        mode_names = self._resolve_modes(modes)
        sample = frames[: max_pairs + 1]
        results: list[CompareResult] = []

        for name in mode_names:
            if name == InferenceMode.DUAL_STREAM.value:
                results.append(CompareResult(mode=name, error="skeleton only"))
                continue
            cfg = replace(self._base_config, mode=name)
            try:
                with RifeInferenceEngine(cfg) as engine:
                    engine.warmup((1, 3, sample[0].shape[2], sample[0].shape[3]))
                    t0 = time.perf_counter()
                    for a, b, t in frame_pairs(sample):
                        engine.interpolate(a, b, t)
                    elapsed = (time.perf_counter() - t0) * 1000.0
                    st = engine.stats()
                    results.append(
                        CompareResult(
                            mode=name,
                            elapsed_ms=elapsed,
                            device_hint=engine.device_hint,
                            npu_hits=st.npu_hits,
                            gpu_hits=st.gpu_hits,
                            fallback_reason=st.fallback_reason,
                            stats={
                                "total_calls": st.total_calls,
                                "total_ms": st.total_ms,
                                "stage_a_ms": st.stage_a_ms,
                                "stage_b_ms": st.stage_b_ms,
                            },
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                results.append(CompareResult(mode=name, error=str(exc)))
        return results

    def benchmark(
        self,
        modes: Iterable[str | InferenceMode] | None = None,
        shape: tuple[int, ...] = (1, 3, 720, 1280),
        iterations: int = 10,
    ) -> list[CompareResult]:
        mode_names = self._resolve_modes(modes)
        img0 = np.random.rand(*shape).astype(np.float32)
        img1 = np.random.rand(*shape).astype(np.float32)
        results: list[CompareResult] = []

        for name in mode_names:
            if name == InferenceMode.DUAL_STREAM.value:
                results.append(CompareResult(mode=name, error="skeleton only"))
                continue
            cfg = replace(self._base_config, mode=name)
            try:
                with RifeInferenceEngine(cfg) as engine:
                    engine.warmup(shape)
                    times: list[float] = []
                    for _ in range(iterations):
                        t0 = time.perf_counter()
                        engine.interpolate(img0, img1)
                        times.append((time.perf_counter() - t0) * 1000.0)
                    st = engine.stats()
                    mean_ms = statistics.mean(times)
                    p95 = sorted(times)[max(0, int(len(times) * 0.95) - 1)]
                    results.append(
                        CompareResult(
                            mode=name,
                            mean_ms=mean_ms,
                            p95_ms=p95,
                            fps=1000.0 / mean_ms if mean_ms > 0 else 0.0,
                            device_hint=engine.device_hint,
                            npu_hits=st.npu_hits,
                            gpu_hits=st.gpu_hits,
                            fallback_reason=st.fallback_reason,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                results.append(CompareResult(mode=name, error=str(exc)))
        return results

    def print_table(self, results: list[CompareResult]) -> None:
        if results and results[0].mean_ms is not None:
            print("| Mode | mean_ms | p95_ms | fps | device | npu | gpu | note |")
            print("|------|---------|--------|-----|--------|-----|-----|------|")
            for r in results:
                if r.error:
                    print(f"| {r.mode} | - | - | - | - | - | - | {r.error} |")
                else:
                    note = r.fallback_reason or ""
                    print(
                        f"| {r.mode} | {r.mean_ms:.2f} | {r.p95_ms:.2f} | {r.fps:.2f} | "
                        f"{r.device_hint} | {r.npu_hits} | {r.gpu_hits} | {note} |"
                    )
        else:
            print("| Mode | elapsed_ms | device | npu | gpu | note |")
            print("|------|------------|--------|-----|-----|------|")
            for r in results:
                if r.error:
                    print(f"| {r.mode} | - | - | - | - | {r.error} |")
                else:
                    note = r.fallback_reason or ""
                    print(
                        f"| {r.mode} | {r.elapsed_ms:.2f} | {r.device_hint} | "
                        f"{r.npu_hits} | {r.gpu_hits} | {note} |"
                    )

    def _resolve_modes(self, modes: Iterable[str | InferenceMode] | None) -> list[str]:
        if modes is None:
            return list_backends()
        out: list[str] = []
        for m in modes:
            out.append(m.value if isinstance(m, InferenceMode) else str(m))
        return out
