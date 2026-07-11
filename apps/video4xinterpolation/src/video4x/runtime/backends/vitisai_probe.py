"""Subprocess probe: VitisAI EP load can native-crash; never do that in-process."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from video4x.runtime.backends._ep_probe import vitisai_cache_key


def probe_vitisai_model_safe(
    model_path: Path,
    *,
    cache_dir: Path | str = "./vitisai_cache",
    timeout_s: float = 1800.0,
    cache_key: str | None = None,
) -> tuple[bool, str]:
    """Return (ok, detail). ok=False if subprocess exits non-zero / times out / crashes."""
    model_path = Path(model_path)
    if not model_path.is_file():
        return False, f"missing model: {model_path}"

    key = cache_key or vitisai_cache_key(model_path)
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    marker = cache / f".vai_ok_{key}"
    if marker.is_file():
        return True, f"cached-ok:{key}"

    script = r"""
import json, sys, os
from pathlib import Path
import numpy as np
import onnxruntime as ort

model = Path(sys.argv[1])
cache = sys.argv[2]
cache_key = sys.argv[3]
so = ort.SessionOptions()
so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
opts = {"cache_dir": cache, "cache_key": cache_key}
install = os.environ.get("RYZEN_AI_INSTALLATION_PATH", "")
if install:
    xclbin = Path(install) / "voe-4.0-win_amd64" / "xclbins" / "phoenix" / "4x4.xclbin"
    if xclbin.is_file():
        opts["target"] = "X1"
        opts["xclbin"] = str(xclbin)
        opts["xlnx_enable_py3_round"] = 0
print(json.dumps({"phase": "load", "cache_key": cache_key}), flush=True)
try:
    sess = ort.InferenceSession(
        str(model),
        sess_options=so,
        providers=[("VitisAIExecutionProvider", opts), "CPUExecutionProvider"],
    )
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}), flush=True)
    sys.exit(2)
prov = sess.get_providers()[0]
if "VitisAI" not in prov:
    print(json.dumps({"ok": False, "error": f"fell back to {prov}"}), flush=True)
    sys.exit(3)
print(json.dumps({"phase": "run", "provider": prov}), flush=True)
feeds = {}
for inp in sess.get_inputs():
    shape = []
    for i, d in enumerate(inp.shape):
        if isinstance(d, int) and d > 0:
            shape.append(d)
        elif i == 0:
            shape.append(1)  # batch
        elif i == 1:
            shape.append(3)  # channels fallback
        else:
            # Dynamic H/W: use 256 (matches preferred fixed SR tile)
            shape.append(256)
    dtype = np.float32
    if inp.type and "float16" in inp.type:
        dtype = np.float16
    feeds[inp.name] = np.zeros(shape, dtype=dtype)
try:
    sess.run(None, feeds)
except Exception as e:
    print(json.dumps({"ok": False, "error": f"run failed: {e}"}), flush=True)
    sys.exit(4)
print(json.dumps({"ok": True, "provider": prov, "cache_key": cache_key}), flush=True)
sys.exit(0)
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(script)
        probe_py = tf.name
    try:
        proc = subprocess.run(
            [sys.executable, probe_py, str(model_path), str(cache), key],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"vitisai probe timed out after {timeout_s:.0f}s"
    finally:
        try:
            Path(probe_py).unlink(missing_ok=True)
        except OSError:
            pass

    if proc.returncode != 0:
        detail = (proc.stdout or "").strip() or (proc.stderr or "").strip() or f"exit={proc.returncode}"
        if not (proc.stdout or "").strip() and proc.returncode not in (2, 3, 4):
            return False, f"vitisai probe crashed (code={proc.returncode})"
        try:
            payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
            return False, str(payload.get("error", detail))
        except Exception:
            return False, detail[:500]

    try:
        payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
        if payload.get("ok"):
            try:
                marker.write_text("ok\n", encoding="utf-8")
            except OSError:
                pass
            return True, str(payload.get("provider", "VitisAI"))
        return False, str(payload.get("error", "unknown"))
    except Exception:
        return False, (proc.stdout or proc.stderr or "parse failed")[:500]
