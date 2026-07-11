"""ONNX Runtime session wrapper with optional pinned-host feeds."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort

from video4x.runtime.backends._ep_probe import build_provider_list, vitisai_cache_key
from video4x.runtime.memory import MemoryPlanner


class OrtSession:
    """Thin ORT InferenceSession wrapper."""

    def __init__(
        self,
        model_path: Path,
        providers: list[str | tuple[str, dict]] | None = None,
        ep_preference: list[str] | None = None,
        fp16: bool = False,
        memory: MemoryPlanner | None = None,
        *,
        cache_dir: str | Path = "./vitisai_cache",
        cache_key: str | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        key = cache_key if cache_key is not None else vitisai_cache_key(self.model_path)
        self.providers = providers or build_provider_list(
            ep_preference,
            fp16=fp16,
            cache_dir=str(cache_dir),
            cache_key=key,
        )
        self._memory = memory
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(self.model_path),
            sess_options=so,
            providers=self.providers,
        )
        self.active_provider = self.session.get_providers()[0]
        self._last_ms = 0.0

    @property
    def input_names(self) -> list[str]:
        return [i.name for i in self.session.get_inputs()]

    @property
    def output_names(self) -> list[str]:
        return [o.name for o in self.session.get_outputs()]

    def run(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        if self._memory is not None:
            feeds = {k: self._memory.ensure(v) for k, v in feeds.items()}
        t0 = time.perf_counter()
        outputs = self.session.run(None, feeds)
        self._last_ms = (time.perf_counter() - t0) * 1000.0
        return dict(zip(self.output_names, outputs))

    def last_elapsed_ms(self) -> float:
        return self._last_ms

    def close(self) -> None:
        del self.session


def make_timestep_array(
    batch: int,
    height: int,
    width: int,
    value: float = 0.5,
    dtype: Any = np.float32,
) -> np.ndarray:
    return np.full((batch, 1, height, width), value, dtype=dtype)
