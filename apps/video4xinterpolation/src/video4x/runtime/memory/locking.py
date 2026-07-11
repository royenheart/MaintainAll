"""Page-lock helpers + common planner base."""

from __future__ import annotations

import ctypes
import sys
from typing import Any

import numpy as np

from video4x.runtime.memory.types import MemoryMode, MemoryProfile


def lock_pages(arr: np.ndarray) -> bool:
    """Best-effort page-lock of *arr* backing store. Returns True if locked."""
    if not isinstance(arr, np.ndarray) or not arr.flags["C_CONTIGUOUS"]:
        return False
    ptr = arr.ctypes.data
    nbytes = arr.nbytes
    if nbytes <= 0:
        return False
    try:
        if sys.platform == "win32":
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            if not kernel32.VirtualLock(ctypes.c_void_p(ptr), ctypes.c_size_t(nbytes)):
                return False
            return True
        libc = ctypes.CDLL(None)
        if libc.mlock(ctypes.c_void_p(ptr), ctypes.c_size_t(nbytes)) != 0:
            return False
        return True
    except Exception:
        return False


def unlock_pages(arr: np.ndarray) -> None:
    if not isinstance(arr, np.ndarray) or not arr.flags["C_CONTIGUOUS"]:
        return
    ptr = arr.ctypes.data
    nbytes = arr.nbytes
    try:
        if sys.platform == "win32":
            ctypes.windll.kernel32.VirtualUnlock(ctypes.c_void_p(ptr), ctypes.c_size_t(nbytes))  # type: ignore[attr-defined]
        else:
            ctypes.CDLL(None).munlock(ctypes.c_void_p(ptr), ctypes.c_size_t(nbytes))
    except Exception:
        pass


class BaseMemoryPlanner:
    def __init__(self) -> None:
        self._mode = MemoryMode.HOST
        self._profile: MemoryProfile | None = None
        self._locked: list[np.ndarray] = []

    def profile(self) -> MemoryProfile:
        if self._profile is None:
            self._profile = self._detect()
        return self._profile

    def _detect(self) -> MemoryProfile:  # pragma: no cover - override
        raise NotImplementedError

    def resolve_mode(self, requested: str | MemoryMode = MemoryMode.AUTO) -> MemoryMode:
        from video4x.runtime.memory.types import parse_memory_mode

        req = parse_memory_mode(requested)
        prof = self.profile()
        if req == MemoryMode.AUTO:
            if prof.has_large_shared_pool or prof.unified_apu:
                self._mode = MemoryMode.SHARED
            else:
                self._mode = MemoryMode.HOST
        elif req == MemoryMode.SHARED:
            # SHARED falls back to pinned locking when no discrete UVM API exists
            self._mode = MemoryMode.SHARED if (prof.has_large_shared_pool or prof.unified_apu) else MemoryMode.PINNED
        else:
            self._mode = req
        return self._mode

    @property
    def mode(self) -> MemoryMode:
        return self._mode

    def allocate(self, shape: tuple[int, ...], *, dtype: Any = np.float32) -> np.ndarray:
        buf = np.empty(shape, dtype=dtype)
        if self._mode in (MemoryMode.PINNED, MemoryMode.SHARED):
            if lock_pages(buf):
                self._locked.append(buf)
        return buf

    def ensure(self, arr: np.ndarray) -> np.ndarray:
        """Return contiguous float32 buffer, page-locked when mode requires it."""
        out = np.ascontiguousarray(arr, dtype=np.float32)
        if self._mode in (MemoryMode.PINNED, MemoryMode.SHARED):
            if out is arr and out.flags["OWNDATA"]:
                if lock_pages(out):
                    self._locked.append(out)
                    return out
            buf = self.allocate(out.shape, dtype=out.dtype)
            np.copyto(buf, out)
            return buf
        return out

    def close(self) -> None:
        for buf in self._locked:
            unlock_pages(buf)
        self._locked.clear()
