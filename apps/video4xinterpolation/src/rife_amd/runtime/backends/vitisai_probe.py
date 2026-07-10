"""Subprocess probe: VitisAI EP load can native-crash; never do that in-process."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def probe_vitisai_model_safe(
    model_path: Path,
    *,
    cache_dir: Path | str = "./vitisai_cache",
    timeout_s: float = 600.0,
) -> tuple[bool, str]:
    """Return (ok, detail). ok=False if subprocess exits non-zero / times out / crashes."""
    model_path = Path(model_path)
    if not model_path.is_file():
        return False, f"missing model: {model_path}"

    # Skip re-probe if a prior successful cache marker exists for this model stem
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    marker = cache / f".vai_ok_{model_path.stem}"
    if marker.is_file():
        return True, f"cached-ok:{model_path.stem}"

    script = r"""
import json, sys, os
from pathlib import Path
import numpy as np
import onnxruntime as ort

model = Path(sys.argv[1])
cache = sys.argv[2]
so = ort.SessionOptions()
so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
opts = {"cache_dir": cache, "cache_key": model.stem}
print(json.dumps({"phase": "load"}), flush=True)
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
    for d in inp.shape:
        if isinstance(d, int) and d > 0:
            shape.append(d)
        else:
            shape.append(1)
    dtype = np.float32
    if inp.type and "float16" in inp.type:
        dtype = np.float16
    feeds[inp.name] = np.zeros(shape, dtype=dtype)
try:
    sess.run(None, feeds)
except Exception as e:
    print(json.dumps({"ok": False, "error": f"run failed: {e}"}), flush=True)
    sys.exit(4)
print(json.dumps({"ok": True, "provider": prov}), flush=True)
sys.exit(0)
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tf:
        tf.write(script)
        probe_py = tf.name
    try:
        proc = subprocess.run(
            [sys.executable, probe_py, str(model_path), str(cache)],
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
