"""Video4x — AMD GPU+NPU video enhance (interpolate + Real-ESRGAN)."""

from video4x.inference import (
    CompareResult,
    InferenceComparator,
    InferenceConfig,
    InferenceMode,
    InferenceResult,
    RifeInferenceEngine,
)
from video4x.job import EnhanceJob, EnhanceJobConfig, EnhanceResult, parse_order
from video4x.ops.base import OpSpec
from video4x.ops.superresolve import SuperResolveConfig, SuperResolveEngine

__version__ = "0.2.0"

__all__ = [
    "CompareResult",
    "EnhanceJob",
    "EnhanceJobConfig",
    "EnhanceResult",
    "InferenceComparator",
    "InferenceConfig",
    "InferenceMode",
    "InferenceResult",
    "OpSpec",
    "RifeInferenceEngine",
    "SuperResolveConfig",
    "SuperResolveEngine",
    "parse_order",
    "__version__",
]
