"""Auto-discover backend modules."""

from video4x.runtime.backends import (
    cpu_baseline,
    dual_stream,
    single_ep,
    split_pipeline,
)

__all__ = ["cpu_baseline", "dual_stream", "single_ep", "split_pipeline"]
