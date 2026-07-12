"""ONNX Runtime session wrapper with optional pinned-host feeds and IOBinding."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort

from video4x.runtime.backends._ep_probe import build_provider_list, vitisai_cache_key
from video4x.runtime.memory import MemoryPlanner


@dataclass
class OrtTensorSlot:
    """Pinned host buffer wrapped as a reusable OrtValue (same data_ptr)."""

    name: str
    array: np.ndarray
    ortvalue: ort.OrtValue

    @property
    def data_ptr(self) -> int:
        return int(self.ortvalue.data_ptr())

    def write(self, src: np.ndarray) -> None:
        """Copy *src* into this slot once (decode / timestep update)."""
        np.copyto(self.array, np.ascontiguousarray(src, dtype=self.array.dtype))

    def numpy_view(self) -> np.ndarray:
        """Zero-copy view of the bound OrtValue buffer."""
        return self.ortvalue.numpy()


def make_ort_slot(
    name: str,
    shape: tuple[int, ...],
    *,
    dtype: Any = np.float32,
    memory: MemoryPlanner | None = None,
) -> OrtTensorSlot:
    if memory is not None:
        buf = memory.allocate(shape, dtype=dtype)
    else:
        buf = np.empty(shape, dtype=dtype)
    if not buf.flags["C_CONTIGUOUS"]:
        buf = np.ascontiguousarray(buf)
    ov = ort.OrtValue.ortvalue_from_numpy(buf)
    return OrtTensorSlot(name=name, array=buf, ortvalue=ov)


@dataclass
class IoBindingBundle:
    """Pre-allocated input/output OrtValues + a Session IOBinding."""

    inputs: dict[str, OrtTensorSlot] = field(default_factory=dict)
    outputs: dict[str, OrtTensorSlot] = field(default_factory=dict)
    binding: Any = None  # ort SessionIOBinding
    fallback_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.binding is not None and self.fallback_reason is None


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

    def input_metas(self) -> list[Any]:
        return list(self.session.get_inputs())

    def output_metas(self) -> list[Any]:
        return list(self.session.get_outputs())

    def run(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        if self._memory is not None:
            feeds = {k: self._memory.ensure(v) for k, v in feeds.items()}
        t0 = time.perf_counter()
        outputs = self.session.run(None, feeds)
        self._last_ms = (time.perf_counter() - t0) * 1000.0
        return dict(zip(self.output_names, outputs))

    def create_binding(self) -> Any:
        return self.session.io_binding()

    def bind_slots(
        self,
        *,
        inputs: dict[str, OrtTensorSlot],
        outputs: dict[str, OrtTensorSlot],
    ) -> IoBindingBundle:
        """Bind preallocated OrtValues; on failure set fallback_reason (no silent zero-copy)."""
        bundle = IoBindingBundle(inputs=inputs, outputs=outputs)
        try:
            iob = self.session.io_binding()
            for name, slot in inputs.items():
                iob.bind_ortvalue_input(name, slot.ortvalue)
            for name, slot in outputs.items():
                iob.bind_ortvalue_output(name, slot.ortvalue)
            bundle.binding = iob
        except Exception as exc:  # noqa: BLE001
            bundle.fallback_reason = (
                f"{self.active_provider} bind_ortvalue failed: {type(exc).__name__}: {exc}"
            )
            bundle.binding = None
        return bundle

    def run_iobinding(self, binding: Any) -> None:
        """Run with a prepared IOBinding. Outputs land in pre-bound OrtValues."""
        t0 = time.perf_counter()
        if hasattr(binding, "synchronize_inputs"):
            binding.synchronize_inputs()
        self.session.run_with_iobinding(binding)
        if hasattr(binding, "synchronize_outputs"):
            binding.synchronize_outputs()
        self._last_ms = (time.perf_counter() - t0) * 1000.0

    def probe_iobinding(
        self,
        feeds: dict[str, np.ndarray],
        *,
        memory: MemoryPlanner | None = None,
    ) -> tuple[bool, str | None, dict[str, tuple[int, ...]]]:
        """
        One-shot probe: allocate slots from *feeds* shapes, bind, run.
        Returns (ok, reason, output_shapes). Does not use copy_outputs_to_cpu as the path.
        """
        mem = memory if memory is not None else self._memory
        in_slots: dict[str, OrtTensorSlot] = {}
        for name, arr in feeds.items():
            slot = make_ort_slot(name, arr.shape, dtype=arr.dtype, memory=mem)
            slot.write(arr)
            in_slots[name] = slot

        # Discover output shapes via a classic run (once), then bind those buffers.
        classic = self.run(feeds)
        out_slots: dict[str, OrtTensorSlot] = {}
        out_shapes: dict[str, tuple[int, ...]] = {}
        for name, arr in classic.items():
            shape = tuple(int(x) for x in arr.shape)
            out_shapes[name] = shape
            out_slots[name] = make_ort_slot(name, shape, dtype=arr.dtype, memory=mem)

        bundle = self.bind_slots(inputs=in_slots, outputs=out_slots)
        if not bundle.ok:
            return False, bundle.fallback_reason, out_shapes

        try:
            self.run_iobinding(bundle.binding)
        except Exception as exc:  # noqa: BLE001
            return (
                False,
                f"{self.active_provider} run_with_iobinding failed: {type(exc).__name__}: {exc}",
                out_shapes,
            )

        # Sanity: OrtValue still points at our host buffer after run.
        for name, slot in out_slots.items():
            if int(slot.ortvalue.data_ptr()) != int(slot.array.ctypes.data):
                return (
                    False,
                    f"{self.active_provider} OrtValue data_ptr drifted for '{name}'",
                    out_shapes,
                )
        return True, None, out_shapes

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
