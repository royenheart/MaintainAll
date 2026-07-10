"""Resource utilization sampling — platform-pluggable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ResourceSample:
    """Point-in-time usage for *this process* where the platform allows it."""

    cpu_percent: float | None = None
    gpu_percent: float | None = None
    npu_percent: float | None = None
    mem_rss_mb: float | None = None
    detail: str = ""  # optional backend note (e.g. counter source)


@runtime_checkable
class ResourceSampler(Protocol):
    """Platform-specific sampler. Implementations may return None for unavailable meters."""

    def sample(self) -> ResourceSample: ...

    def close(self) -> None: ...


class NullResourceSampler:
    """No-op sampler (tests / unsupported hosts)."""

    def sample(self) -> ResourceSample:
        return ResourceSample(detail="null")

    def close(self) -> None:
        return None
