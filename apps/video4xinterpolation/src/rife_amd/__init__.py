"""Compatibility shim — prefer ``import video4x``.

Submodule imports (``rife_amd.runtime`` etc.) are aliased to ``video4x.*``.
"""

from __future__ import annotations

import sys

import video4x as _video4x

# Alias common subpackages so ``from rife_amd.X import Y`` keeps working.
for _name in (
    "inference",
    "runtime",
    "model",
    "quant",
    "cli",
    "onnx_export",
    "onnx_rewrite",
    "ops",
    "job",
    "tui",
):
    _full_v = f"video4x.{_name}"
    _full_r = f"rife_amd.{_name}"
    if _full_v in sys.modules:
        sys.modules[_full_r] = sys.modules[_full_v]
    else:
        try:
            _mod = __import__(_full_v, fromlist=["*"])
            sys.modules[_full_r] = _mod
            # Also alias nested modules already loaded under video4x
            for _k, _m in list(sys.modules.items()):
                if _k.startswith(_full_v + "."):
                    sys.modules[_full_r + _k[len(_full_v) :]] = _m
        except ImportError:
            pass

from video4x import (  # noqa: E402, F401
    CompareResult,
    InferenceComparator,
    InferenceConfig,
    InferenceMode,
    InferenceResult,
    RifeInferenceEngine,
    __version__,
)

__all__ = [
    "CompareResult",
    "InferenceComparator",
    "InferenceConfig",
    "InferenceMode",
    "InferenceResult",
    "RifeInferenceEngine",
    "__version__",
]
