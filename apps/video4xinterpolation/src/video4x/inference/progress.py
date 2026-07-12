"""Lightweight inference progress events (engine layer, backend-agnostic)."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field, replace
from typing import Callable, TextIO

from video4x.runtime.resources.base import ResourceSampler


@dataclass(frozen=True)
class ProgressEvent:
    """One progress tick from RifeInferenceEngine (not backend-specific)."""

    phase: str  # decode | init | interpolate | encode | done
    message: str = ""
    current: int = 0
    total: int = 0
    elapsed_s: float = 0.0
    eta_s: float | None = None
    mode: str = ""
    device_hint: str = ""
    providers: dict[str, str] = field(default_factory=dict)
    last_ms: float = 0.0
    avg_ms: float = 0.0
    gpu_hits: int = 0
    npu_hits: int = 0
    stage_a_ms: float = 0.0
    stage_b_ms: float = 0.0
    # Process resource sample (platform sampler; None = unavailable)
    cpu_percent: float | None = None
    gpu_percent: float | None = None
    npu_percent: float | None = None
    mem_rss_mb: float | None = None
    memory_mode: str = ""
    memory_detail: str = ""

    @property
    def pct(self) -> float:
        if self.total <= 0:
            return 0.0
        return 100.0 * self.current / self.total


ProgressCallback = Callable[[ProgressEvent], None]


def format_progress_line(ev: ProgressEvent) -> str:
    """Single-line human summary for stdout / logs."""
    parts: list[str] = [f"[{ev.phase}]"]
    if ev.total > 0:
        parts.append(f"{ev.current}/{ev.total} ({ev.pct:.0f}%)")
    if ev.message:
        parts.append(ev.message)
    if ev.mode:
        parts.append(f"mode={ev.mode}")
    if ev.device_hint:
        parts.append(f"hint={ev.device_hint}")
    if ev.providers:
        prov = ",".join(f"{k}={_short_ep(v)}" for k, v in ev.providers.items())
        parts.append(f"ep=[{prov}]")
    if ev.last_ms > 0 or ev.avg_ms > 0:
        parts.append(f"last={ev.last_ms:.0f}ms avg={ev.avg_ms:.0f}ms")
    if ev.stage_a_ms or ev.stage_b_ms:
        parts.append(f"A={ev.stage_a_ms:.0f}ms B={ev.stage_b_ms:.0f}ms")
    if ev.gpu_hits or ev.npu_hits:
        parts.append(f"gpu_hits={ev.gpu_hits} npu_hits={ev.npu_hits}")
    res_bits: list[str] = []
    if ev.cpu_percent is not None:
        res_bits.append(f"CPU={ev.cpu_percent:.0f}%")
    if ev.gpu_percent is not None:
        res_bits.append(f"GPU={ev.gpu_percent:.0f}%")
    elif any("Dml" in v or "ROCM" in v for v in ev.providers.values()):
        res_bits.append("GPU=n/a")
    if ev.npu_percent is not None:
        res_bits.append(f"NPU={ev.npu_percent:.0f}%")
    elif any("VitisAI" in v for v in ev.providers.values()):
        # EP selected VitisAI but OS counter missing / not attributed to this PID
        res_bits.append("NPU=n/a")
    if ev.mem_rss_mb is not None:
        res_bits.append(f"RSS={ev.mem_rss_mb:.0f}MB")
    if res_bits:
        parts.append("res=[" + ",".join(res_bits) + "]")
    if ev.memory_mode:
        parts.append(f"mem={ev.memory_mode}")
    if ev.eta_s is not None:
        parts.append(f"ETA={_fmt_secs(ev.eta_s)}")
    if ev.elapsed_s > 0 and ev.phase == "done":
        parts.append(f"elapsed={_fmt_secs(ev.elapsed_s)}")
    return " | ".join(parts)


def _short_ep(name: str) -> str:
    return name.replace("ExecutionProvider", "")


def _fmt_secs(s: float) -> str:
    if s < 60:
        return f"{s:.0f}s"
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{sec:02d}s"


class StdoutProgressReporter:
    """Default CLI reporter: phase changes on new lines, interpolate uses \\r."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stderr
        self._last_phase: str | None = None

    def __call__(self, ev: ProgressEvent) -> None:
        line = format_progress_line(ev)
        if ev.phase == "interpolate" and ev.total > 0 and ev.current < ev.total:
            if self._last_phase and self._last_phase != "interpolate":
                self._stream.write("\n")
            # \x1b[K clears to end of line so longer→shorter updates don't leave garbage
            self._stream.write("\r" + line + "\x1b[K")
            self._stream.flush()
        else:
            if self._last_phase == "interpolate":
                self._stream.write("\n")
            self._stream.write(line + "\n")
            self._stream.flush()
        self._last_phase = ev.phase


class ProgressTracker:
    """Helper used by the engine to build events with ETA / averages / resources."""

    def __init__(
        self,
        on_progress: ProgressCallback | None,
        sampler: ResourceSampler | None = None,
    ) -> None:
        self._on = on_progress
        self._sampler = sampler
        self.t0 = time.perf_counter()
        self._last_total_ms = 0.0

    def emit(self, ev: ProgressEvent) -> None:
        if self._on is None:
            return
        if self._sampler is not None:
            s = self._sampler.sample()
            ev = replace(
                ev,
                cpu_percent=s.cpu_percent,
                gpu_percent=s.gpu_percent,
                npu_percent=s.npu_percent,
                mem_rss_mb=s.mem_rss_mb,
            )
        self._on(ev)

    def close(self) -> None:
        if self._sampler is not None:
            self._sampler.close()
            self._sampler = None

    def elapsed(self) -> float:
        return time.perf_counter() - self.t0

    def pair_timing(self, total_ms: float, pairs_done: int) -> tuple[float, float, float | None]:
        """Return (last_ms, avg_ms, eta_s_for_remaining) given cumulative backend total_ms."""
        last = max(0.0, total_ms - self._last_total_ms)
        self._last_total_ms = total_ms
        avg = total_ms / pairs_done if pairs_done else 0.0
        return last, avg, None

    def eta(self, pairs_done: int, pairs_total: int, avg_ms: float) -> float | None:
        if pairs_done <= 0 or pairs_total <= pairs_done or avg_ms <= 0:
            return None
        return (pairs_total - pairs_done) * (avg_ms / 1000.0)
