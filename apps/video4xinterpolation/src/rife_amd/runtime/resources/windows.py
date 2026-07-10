"""Windows resource sampler (process CPU/RSS + GPU/NPU engine counters)."""

from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Any

from rife_amd.runtime.resources.base import ResourceSample

_PID = os.getpid()

# Cached discovery of NPU counter paths (machine-dependent).
_NPU_PATHS: list[str] | None = None


class WindowsResourceSampler:
    """Sample this process on Windows.

    - CPU / RSS: ``psutil``
    - GPU: ``\\GPU Engine(*)\\Utilization Percentage`` filtered by this PID
    - NPU: discover counter sets matching NPU/XDNA/Neural; prefer PID instances,
      else report **system-wide** max (so progress can show NPU=%% at all)
    """

    def __init__(self, min_interval_s: float = 0.5) -> None:
        self._min_interval = min_interval_s
        self._last_t = 0.0
        self._cached = ResourceSample(detail="windows:init")
        self._proc: Any = None
        try:
            import psutil

            self._proc = psutil.Process(_PID)
            self._proc.cpu_percent(None)
        except Exception:
            self._proc = None

    def sample(self) -> ResourceSample:
        now = time.perf_counter()
        if now - self._last_t < self._min_interval and self._last_t > 0:
            return self._cached
        self._last_t = now

        cpu = mem = None
        detail_parts: list[str] = ["windows"]
        if self._proc is not None:
            try:
                cpu = float(self._proc.cpu_percent(None))
                mem = float(self._proc.memory_info().rss) / (1024 * 1024)
            except Exception:
                detail_parts.append("psutil_fail")
        else:
            detail_parts.append("no_psutil")

        gpu, npu, gnote = _sample_engine_counters(_PID)
        if gnote:
            detail_parts.append(gnote)

        self._cached = ResourceSample(
            cpu_percent=cpu,
            gpu_percent=gpu,
            npu_percent=npu,
            mem_rss_mb=mem,
            detail="+".join(detail_parts),
        )
        return self._cached

    def close(self) -> None:
        self._proc = None


def _discover_npu_counter_paths() -> list[str]:
    """Known NPU counter paths (avoid slow ``Get-Counter -ListSet *``)."""
    global _NPU_PATHS
    if _NPU_PATHS is not None:
        return _NPU_PATHS
    _NPU_PATHS = [
        r"\NPU Engine(*)\Utilization Percentage",
        r"\NPU Engine(*)\Usage",
        r"\Neural Processor(*)\Utilization Percentage",
        r"\Intel(R) AI Boost(*)\Utilization Percentage",
    ]
    return _NPU_PATHS


def _sample_engine_counters(pid: int) -> tuple[float | None, float | None, str]:
    """Return (gpu%, npu%, note)."""
    npu_paths = _discover_npu_counter_paths()
    # Build PowerShell array of paths
    ps_paths = "@(" + ",".join(f"'{p.replace(chr(39), chr(39)+chr(39))}'" for p in npu_paths) + ")"
    script = f"""
$targetPid = {pid}
$gpu = 0.0; $npu = 0.0; $g = 0; $n = 0; $nSys = 0
try {{
  $c = Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue
  if ($c) {{
    foreach ($s in $c.CounterSamples) {{
      $inst = [string]$s.InstanceName
      $val = [double]$s.CookedValue
      if ($inst -match ("pid_" + $targetPid + "_")) {{
        $gpu = [Math]::Max($gpu, $val); $g++
        # Some AMD stacks label NPU work as engtype_NPU / Copy / Compute under GPU Engine
        if ($inst -match '(?i)engtype_NPU|engtype_HardwareQueue|npu') {{
          $npu = [Math]::Max($npu, $val); $n++
        }}
      }}
    }}
  }}
}} catch {{}}
foreach ($path in {ps_paths}) {{
  try {{
    $c2 = Get-Counter $path -ErrorAction SilentlyContinue
    if (-not $c2) {{ continue }}
    foreach ($s in $c2.CounterSamples) {{
      $inst = [string]$s.InstanceName
      $val = [double]$s.CookedValue
      if ($val -lt 0) {{ continue }}
      if ($inst -match ("pid_" + $targetPid + "_")) {{
        $npu = [Math]::Max($npu, $val); $n++
      }} elseif ($path -match '(?i)NPU|XDNA|Neural|AI Boost|VPU') {{
        $npu = [Math]::Max($npu, $val); $nSys++
      }}
    }}
  }} catch {{}}
}}
if ($n -eq 0 -and $nSys -gt 0) {{ $n = $nSys }}
Write-Output ("GPU={{0}};NPU={{1}};G={{2}};N={{3}};NS={{4}}" -f $gpu, $npu, $g, $n, $nSys)
"""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, None, f"counter_err:{type(exc).__name__}"

    out = (proc.stdout or "").strip().splitlines()
    if not out:
        err = (proc.stderr or "")[:80]
        return None, None, f"counter_empty:{err}"
    line = out[-1]
    m = re.search(
        r"GPU=([0-9.]+);NPU=([0-9.]+);G=(\d+);N=(\d+);NS=(\d+)",
        line,
    )
    if not m:
        return None, None, f"counter_parse:{line[:60]}"
    gpu_v = float(m.group(1))
    npu_v = float(m.group(2))
    g_n, n_n, n_sys = int(m.group(3)), int(m.group(4)), int(m.group(5))
    gpu = gpu_v if g_n > 0 else None
    # Report NPU even when only system-wide samples exist (NS>0)
    npu = npu_v if n_n > 0 else None
    note = f"eng_g={g_n},eng_n={n_n},npu_sys={n_sys}"
    return gpu, npu, note
