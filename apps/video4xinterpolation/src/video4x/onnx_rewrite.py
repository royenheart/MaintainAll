"""Post-export ONNX rewrites: slim HxW Constants → ConstantOfShape / CumSum."""

from __future__ import annotations

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper


def rewrite_spatial_constants_to_ops(model: onnx.ModelProto, height: int, width: int) -> int:
    """Replace large all-ones / index-grid Constants+initializers with tiny ops.

    Returns number of tensors rewritten. Keeps VitisAI-friendly structure
    (explicit ones / arange via ConstantOfShape+CumSum) without multi-MB tensors.
    """
    graph = model.graph
    rewritten = 0

    # --- Constant nodes ---
    const_nodes = [n for n in graph.node if n.op_type == "Constant"]
    replacements: list[tuple[onnx.NodeProto, list[onnx.NodeProto], list[onnx.TensorProto]]] = []

    for node in const_nodes:
        arr = _constant_to_array(node)
        if arr is None:
            continue
        built = _build_replacement(node.output[0], arr, height, width)
        if built is None:
            continue
        new_nodes, inits = built
        replacements.append((node, new_nodes, inits))

    if replacements:
        remove_outs = {n.output[0] for n, _, _ in replacements}
        new_node_list: list[onnx.NodeProto] = []
        for n in graph.node:
            if n.op_type == "Constant" and n.output[0] in remove_outs:
                continue
            new_node_list.append(n)

        insert_at = 0
        for _old, news, inits in replacements:
            for init in inits:
                if not any(i.name == init.name for i in graph.initializer):
                    graph.initializer.append(init)
            for nn in news:
                new_node_list.insert(insert_at, nn)
                insert_at += 1
            rewritten += 1

        del graph.node[:]
        graph.node.extend(new_node_list)

    # --- Initializers (folded weights / grids) ---
    init_replacements: list[tuple[str, list[onnx.NodeProto], list[onnx.TensorProto]]] = []
    for init in list(graph.initializer):
        try:
            arr = numpy_helper.to_array(init)
        except Exception:
            continue
        built = _build_replacement(init.name, arr, height, width)
        if built is None:
            continue
        new_nodes, inits = built
        init_replacements.append((init.name, new_nodes, inits))

    if init_replacements:
        drop = {name for name, _, _ in init_replacements}
        keep = [i for i in graph.initializer if i.name not in drop]
        del graph.initializer[:]
        graph.initializer.extend(keep)
        # Prepend ops so consumers see the tensor name
        prepend: list[onnx.NodeProto] = []
        for _name, news, inits in init_replacements:
            for init in inits:
                if not any(i.name == init.name for i in graph.initializer):
                    graph.initializer.append(init)
            prepend.extend(news)
            rewritten += 1
        new_nodes = list(prepend) + list(graph.node)
        del graph.node[:]
        graph.node.extend(new_nodes)

    _strip_unused_spatial_initializers(model, height, width)
    return rewritten


def _build_replacement(
    out_name: str, arr: np.ndarray, height: int, width: int
) -> tuple[list[onnx.NodeProto], list[onnx.TensorProto]] | None:
    if arr.shape == (1, 1, height, width) and _is_ones(arr):
        return _make_ones_subgraph(out_name, height, width)
    if arr.shape == (1, 1, height, width) and _is_horiz_index(arr, height, width):
        return _make_arange_subgraph(out_name, height, width, axis=3)
    if arr.shape == (1, 1, height, width) and _is_vert_index(arr, height, width):
        return _make_arange_subgraph(out_name, height, width, axis=2)
    return None


def _constant_to_array(node: onnx.NodeProto) -> np.ndarray | None:
    for attr in node.attribute:
        if attr.name == "value" and attr.t.ByteSize() > 0:
            return numpy_helper.to_array(attr.t)
    return None


def _is_ones(arr: np.ndarray) -> bool:
    return arr.size > 0 and np.allclose(arr, 1.0)


def _is_horiz_index(arr: np.ndarray, height: int, width: int) -> bool:
    if arr.shape != (1, 1, height, width):
        return False
    row = np.arange(width, dtype=np.float64)
    for h in range(min(height, 8)):
        if not np.allclose(arr[0, 0, h, :].astype(np.float64), row):
            return False
    return True


def _is_vert_index(arr: np.ndarray, height: int, width: int) -> bool:
    if arr.shape != (1, 1, height, width):
        return False
    col = np.arange(height, dtype=np.float64)
    for w in range(min(width, 8)):
        if not np.allclose(arr[0, 0, :, w].astype(np.float64), col):
            return False
    return True


def _make_ones_subgraph(
    out_name: str, height: int, width: int
) -> tuple[list[onnx.NodeProto], list[onnx.TensorProto]]:
    shape_name = f"{out_name}__shape"
    shape_init = numpy_helper.from_array(
        np.array([1, 1, height, width], dtype=np.int64), name=shape_name
    )
    value = helper.make_tensor("value", TensorProto.FLOAT, [1], [1.0])
    node = helper.make_node(
        "ConstantOfShape",
        inputs=[shape_name],
        outputs=[out_name],
        name=f"{out_name}__cos",
        value=value,
    )
    return [node], [shape_init]


def _make_arange_subgraph(
    out_name: str, height: int, width: int, *, axis: int
) -> tuple[list[onnx.NodeProto], list[onnx.TensorProto]]:
    ones_name = f"{out_name}__ones"
    axis_name = f"{out_name}__axis"
    ones_nodes, ones_inits = _make_ones_subgraph(ones_name, height, width)
    axis_init = numpy_helper.from_array(np.array([axis], dtype=np.int64), name=axis_name)
    cum = helper.make_node(
        "CumSum",
        inputs=[ones_name, axis_name],
        outputs=[f"{out_name}__cum"],
        name=f"{out_name}__cumsum",
    )
    one_name = f"{out_name}__one_scalar"
    one_init = numpy_helper.from_array(np.array(1.0, dtype=np.float32), name=one_name)
    sub = helper.make_node(
        "Sub",
        inputs=[f"{out_name}__cum", one_name],
        outputs=[out_name],
        name=f"{out_name}__sub",
    )
    return ones_nodes + [cum, sub], ones_inits + [axis_init, one_init]


def _strip_unused_spatial_initializers(model: onnx.ModelProto, height: int, width: int) -> int:
    used: set[str] = set()
    for n in model.graph.node:
        used.update(i for i in n.input if i)
    for out in model.graph.output:
        used.add(out.name)
    spatial = {
        (1, 1, height, width),
        (1, 2, height, width),
        (1, 3, height, width),
        (1, 4, height, width),
    }
    keep = []
    removed = 0
    for init in model.graph.initializer:
        dims = tuple(init.dims)
        if dims in spatial and init.name not in used:
            removed += 1
            continue
        keep.append(init)
    if removed:
        del model.graph.initializer[:]
        model.graph.initializer.extend(keep)
    return removed


def summarize_large_constants(model: onnx.ModelProto, min_elems: int = 100_000) -> list[str]:
    """Debug helper: list Constant / initializer tensors above *min_elems*."""
    lines: list[str] = []
    for init in model.graph.initializer:
        n = int(np.prod(init.dims)) if init.dims else 0
        if n >= min_elems:
            lines.append(f"init {init.name} dims={list(init.dims)} elems={n}")
    for node in model.graph.node:
        if node.op_type != "Constant":
            continue
        arr = _constant_to_array(node)
        if arr is not None and arr.size >= min_elems:
            lines.append(f"const {node.output[0]} shape={list(arr.shape)} elems={arr.size}")
    return lines
