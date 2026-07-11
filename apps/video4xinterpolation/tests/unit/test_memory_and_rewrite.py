"""Unit tests for memory planner + ONNX spatial rewrite."""

from __future__ import annotations

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

from video4x.onnx_rewrite import rewrite_spatial_constants_to_ops, summarize_large_constants
from video4x.runtime.memory import create_memory_planner, parse_memory_mode
from video4x.runtime.memory.types import MemoryMode


def test_parse_memory_mode() -> None:
    assert parse_memory_mode("auto") == MemoryMode.AUTO
    assert parse_memory_mode("PINNED") == MemoryMode.PINNED


def test_memory_planner_resolve_auto() -> None:
    planner = create_memory_planner("windows")
    mode = planner.resolve_mode("auto")
    assert mode in (MemoryMode.HOST, MemoryMode.SHARED, MemoryMode.PINNED)
    prof = planner.profile()
    assert prof.system_ram_mb >= 0
    buf = planner.allocate((2, 3), dtype=np.float32)
    assert buf.shape == (2, 3)
    planner.close()


def test_rewrite_ones_constant() -> None:
    h, w = 32, 48
    ones = np.ones((1, 1, h, w), dtype=np.float32)
    const = helper.make_node(
        "Constant",
        inputs=[],
        outputs=["ones"],
        value=numpy_helper.from_array(ones, name="ones_t"),
    )
    identity = helper.make_node("Identity", ["ones"], ["out"])
    graph = helper.make_graph(
        [const, identity],
        "g",
        [],
        [helper.make_tensor_value_info("out", TensorProto.FLOAT, [1, 1, h, w])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    n = rewrite_spatial_constants_to_ops(model, h, w)
    assert n >= 1
    assert not summarize_large_constants(model, min_elems=100)
    assert any(node.op_type == "ConstantOfShape" for node in model.graph.node)
    onnx.checker.check_model(model)
