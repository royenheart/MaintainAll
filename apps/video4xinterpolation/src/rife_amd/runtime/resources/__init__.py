"""Resource utilization sampling — platform-pluggable."""

from __future__ import annotations

from rife_amd.runtime.resources.base import (
    NullResourceSampler,
    ResourceSample,
    ResourceSampler,
)

__all__ = [
    "NullResourceSampler",
    "ResourceSample",
    "ResourceSampler",
    "create_resource_sampler",
]


def create_resource_sampler(platform: str | None = None) -> ResourceSampler:
    """Factory: pick sampler for host platform (auto-detect if platform is None/auto)."""
    from rife_amd.runtime.platform import HostPlatform, resolve_platform

    plat = resolve_platform(platform)
    if plat == HostPlatform.WINDOWS:
        from rife_amd.runtime.resources.windows import WindowsResourceSampler

        return WindowsResourceSampler()
    if plat in (HostPlatform.LINUX, HostPlatform.WSL):
        from rife_amd.runtime.resources.linux import LinuxResourceSampler

        return LinuxResourceSampler(wsl=(plat == HostPlatform.WSL))
    return NullResourceSampler()
