"""Backend registry with auto-discovery."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Type

from rife_amd.runtime.backends.base import InterpolationBackend

_REGISTRY: dict[str, Type[InterpolationBackend]] = {}
_DISCOVERED = False


def register_backend(name: str):
    """Decorator to register an InterpolationBackend implementation."""

    def decorator(cls: Type[InterpolationBackend]) -> Type[InterpolationBackend]:
        _REGISTRY[name] = cls
        cls.name = name  # type: ignore[attr-defined]
        return cls

    return decorator


def _discover() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return
    import rife_amd.runtime.backends as backends_pkg

    for mod in pkgutil.iter_modules(backends_pkg.__path__, backends_pkg.__name__ + "."):
        if mod.name.endswith(("_ep_probe", "base", "registry")):
            continue
        importlib.import_module(mod.name)
    _DISCOVERED = True


def list_backends() -> list[str]:
    _discover()
    return sorted(_REGISTRY.keys())


def get_backend(name: str) -> Type[InterpolationBackend]:
    _discover()
    if name not in _REGISTRY:
        raise KeyError(f"Unknown backend '{name}'. Available: {', '.join(list_backends())}")
    return _REGISTRY[name]


def create_backend(name: str) -> InterpolationBackend:
    return get_backend(name)()
