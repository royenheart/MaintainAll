"""RIFE AMD: ONNX-based video interpolation on AMD GPU + NPU."""

from rife_amd.inference import (
    CompareResult,
    InferenceComparator,
    InferenceConfig,
    InferenceMode,
    InferenceResult,
    RifeInferenceEngine,
)

__version__ = "0.1.0"

__all__ = [
    "CompareResult",
    "InferenceComparator",
    "InferenceConfig",
    "InferenceMode",
    "InferenceResult",
    "RifeInferenceEngine",
    "__version__",
]
