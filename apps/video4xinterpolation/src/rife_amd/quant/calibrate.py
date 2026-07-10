"""Calibration data generation for Stage B Quark quantization."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort

from rife_amd.runtime.session import make_timestep_array


def generate_calibration_samples(
    stage_a_onnx: Path,
    num_pairs: int = 8,
    height: int = 360,
    width: int = 640,
    seed: int = 42,
) -> list[dict[str, np.ndarray]]:
    """Run random frame pairs through Stage A to produce Stage B calibration inputs."""
    rng = np.random.default_rng(seed)
    session = ort.InferenceSession(str(stage_a_onnx), providers=["CPUExecutionProvider"])
    out_names = [o.name for o in session.get_outputs()]
    samples: list[dict[str, np.ndarray]] = []

    for _ in range(num_pairs):
        img0 = rng.random((1, 3, height, width), dtype=np.float32)
        img1 = rng.random((1, 3, height, width), dtype=np.float32)
        ts = make_timestep_array(1, height, width, 0.5)
        outputs = session.run(None, {"img0": img0, "img1": img1, "timestep": ts})
        a_map = dict(zip(out_names, outputs))
        b_sample = {
            "img0": img0,
            "img1": img1,
            "flow": a_map["flow"],
            "mask": a_map["mask"],
            "feat": a_map["feat"],
            "warped_img0": a_map["warped_img0"],
            "warped_img1": a_map["warped_img1"],
            "f0": a_map["f0"],
            "f1": a_map["f1"],
            "timestep": a_map.get("timestep_out", ts),
        }
        samples.append(b_sample)
    return samples


def save_calibration_npz(samples: list[dict[str, np.ndarray]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, samples=np.array(samples, dtype=object))
