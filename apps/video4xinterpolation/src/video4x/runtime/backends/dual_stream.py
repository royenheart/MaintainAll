"""Dual-stream: overlap Stage A(N+1) GPU with Stage B(N) NPU across pairs.

Windows-first concurrent scheduling via ThreadPoolExecutor. Non-Windows falls
back to sequential split-pipeline behavior (same sessions, no cross-pair overlap).

When ``memory_mode=shared`` (or ``use_iobinding=True``), Stage A/B share pinned
OrtValue slots via IOBinding (double-buffered). Concurrent DirectML Stage A with
Stage B ``run_with_iobinding`` is unsafe, so ``interpolate_pairs`` keeps IOBinding
zero-copy but runs A→B sequentially; classic (non-IOBinding) dual-stream still overlaps.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock

import numpy as np

from video4x.runtime.backends._split_sessions import (
    PreparedPair,
    SplitSessions,
    is_gpu_provider,
)
from video4x.runtime.backends.base import BackendConfig, BackendStats
from video4x.runtime.backends.registry import register_backend
from video4x.runtime.platform import HostPlatform, resolve_platform


@register_backend("dual-stream")
class DualStreamBackend:
    """
    Concurrent dual-stream RIFE backend.

    - ``interpolate``: sequential A→B for a single pair (API-compatible).
    - ``interpolate_pairs``: pipelines A(N+1) with B(N) when ``supports_pair_pipeline``
      and IOBinding is off; with IOBinding, pairs stay sequential (zero-copy intact).
    """

    name = "dual-stream"
    supports_npu = False
    supports_gpu = False
    device_hint = "mixed"
    supports_pair_pipeline = False

    def __init__(self) -> None:
        self._sessions = SplitSessions()
        self._stats = BackendStats()
        self._stats_lock = Lock()
        self._pool: ThreadPoolExecutor | None = None
        self._pipeline_enabled = False
        self._overlap_deferred_note: str | None = None

    def init(self, cfg: BackendConfig) -> None:
        plat = resolve_platform(cfg.platform)
        self._sessions.init(cfg)
        self.supports_gpu = self._sessions.supports_gpu
        self.supports_npu = self._sessions.supports_npu
        self._sessions.apply_stats_meta(self._stats)

        if plat == HostPlatform.WINDOWS:
            self._pipeline_enabled = True
            self.supports_pair_pipeline = True
            self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dual-stream")
        else:
            self._pipeline_enabled = False
            self.supports_pair_pipeline = False
            note = (
                f"dual-stream concurrent pipeline is Windows-only "
                f"(platform={plat.value}); using sequential split"
            )
            self._stats.fallback_reason = (
                f"{self._stats.fallback_reason}; {note}"
                if self._stats.fallback_reason
                else note
            )

    def _record_stage_a(self) -> float:
        a_ms = self._sessions.stage_a_ms()
        with self._stats_lock:
            self._stats.stage_a_ms += a_ms
            assert self._sessions.stage_a is not None
            if is_gpu_provider(self._sessions.stage_a.active_provider):
                self._stats.gpu_hits += 1
        return a_ms

    def _record_stage_b(self) -> float:
        b_ms = self._sessions.stage_b_ms()
        with self._stats_lock:
            self._stats.stage_b_ms += b_ms
            assert self._sessions.stage_b is not None
            if "VitisAI" in self._sessions.stage_b.active_provider:
                self._stats.npu_hits += 1
        return b_ms

    def _note_overlap_deferred(self) -> None:
        if self._overlap_deferred_note is not None:
            return
        self._overlap_deferred_note = (
            "dual-stream ORT overlap disabled under IOBinding "
            "(DirectML Stage A concurrent with VitisAI IOBinding is unsafe)"
        )
        with self._stats_lock:
            self._stats.fallback_reason = (
                f"{self._stats.fallback_reason}; {self._overlap_deferred_note}"
                if self._stats.fallback_reason
                else self._overlap_deferred_note
            )

    def _run_ab(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        timestep: float,
    ) -> np.ndarray:
        prep = self._sessions.prepare_pair(img0, img1, timestep)
        try:
            a_out = self._sessions.run_stage_a(prep)
            a_ms = self._record_stage_a()
            merged = self._sessions.run_stage_b(prep, a_out)
            b_ms = self._record_stage_b()
            with self._stats_lock:
                self._stats.total_calls += 1
                self._stats.total_ms += a_ms + b_ms
            return merged
        except Exception:
            prep.release()
            raise

    def interpolate(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        timestep: float = 0.5,
        scale: float = 1.0,
    ) -> np.ndarray:
        del scale
        return self._run_ab(img0, img1, timestep)

    def _stage_b_job(
        self,
        prep: PreparedPair,
        a_out: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, float]:
        merged = self._sessions.run_stage_b(prep, a_out)
        b_ms = self._record_stage_b()
        return merged, b_ms

    def interpolate_pairs(
        self,
        pairs: Iterable[tuple[np.ndarray, np.ndarray]],
        timestep: float = 0.5,
        scale: float = 1.0,
    ) -> Iterator[np.ndarray]:
        """Yield mid-frames for each consecutive pair.

        On Windows with the thread pool enabled and IOBinding off, Stage A of
        pair N+1 overlaps Stage B of pair N. With IOBinding on, pairs run
        sequential A→B (shared OrtValue zero-copy) because DirectML cannot
        safely run Stage A while Stage B uses ``run_with_iobinding``.
        """
        del scale
        pair_list = list(pairs)
        if not pair_list:
            return

        if not self._pipeline_enabled or self._pool is None:
            for img0, img1 in pair_list:
                yield self._run_ab(img0, img1, timestep)
            return

        # Warm IOBinding on the first pair before choosing a schedule.
        held: PreparedPair | None = self._sessions.prepare_pair(
            pair_list[0][0], pair_list[0][1], timestep
        )
        if self._sessions.use_iobinding:
            self._note_overlap_deferred()
            try:
                assert held is not None
                a_out = self._sessions.run_stage_a(held)
                a_ms = self._record_stage_a()
                merged = self._sessions.run_stage_b(held, a_out)
                held = None
                b_ms = self._record_stage_b()
                with self._stats_lock:
                    self._stats.total_calls += 1
                    self._stats.total_ms += a_ms + b_ms
                yield merged
                for img0, img1 in pair_list[1:]:
                    yield self._run_ab(img0, img1, timestep)
            except Exception:
                if held is not None:
                    held.release()
                raise
            return

        try:
            assert held is not None
            a_out = self._sessions.run_stage_a(held)
            a_ms_pending = self._record_stage_a()

            n = len(pair_list)
            for i in range(n):
                assert held is not None
                b_future: Future[tuple[np.ndarray, float]] = self._pool.submit(
                    self._stage_b_job, held, a_out
                )
                # Stage B owns slot release for *held*.
                held = None
                next_a_ms = 0.0
                next_held: PreparedPair | None = None
                next_a_out = None
                try:
                    if i + 1 < n:
                        next_held = self._sessions.prepare_pair(
                            pair_list[i + 1][0], pair_list[i + 1][1], timestep
                        )
                        # Overlaps Stage B(N) running on the pool thread.
                        next_a_out = self._sessions.run_stage_a(next_held)
                        next_a_ms = self._record_stage_a()
                except Exception:
                    if next_held is not None:
                        next_held.release()
                    raise
                finally:
                    # Always join Stage B before leaving this iteration (incl. errors),
                    # so the Stage-B OrtSession is never re-entered concurrently.
                    merged, b_ms = b_future.result()

                with self._stats_lock:
                    self._stats.total_calls += 1
                    self._stats.total_ms += a_ms_pending + b_ms
                yield merged

                if next_held is not None and next_a_out is not None:
                    held = next_held
                    a_out = next_a_out
                    a_ms_pending = next_a_ms
                else:
                    break
        except Exception:
            if held is not None:
                held.release()
            raise

    def warmup(self, shape: tuple[int, ...] = (1, 3, 1080, 1920)) -> None:
        self.interpolate(
            np.random.rand(*shape).astype(np.float32),
            np.random.rand(*shape).astype(np.float32),
        )

    def teardown(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=False)
            self._pool = None
        self._pipeline_enabled = False
        self.supports_pair_pipeline = False
        self._sessions.close()

    def stats(self) -> BackendStats:
        # Refresh iobinding flags that may flip after first-frame warmup.
        self._sessions.apply_stats_meta(self._stats)
        return self._stats
