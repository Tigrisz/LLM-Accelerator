"""Quantize and package one real W4A8 linear-layer slice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .golden_gemv import gemv_partial_sums
from .pack_weights import pack_weight_matrix
from .stream_reference import iter_gemv_beats


def quantize_weights_groupwise(weights: np.ndarray, group_size: int = 128) -> tuple[np.ndarray, np.ndarray]:
    """Symmetric INT4 quantization with one scale per row/group."""
    if weights.ndim != 2 or weights.shape[1] == 0 or weights.shape[1] % group_size:
        raise ValueError("weights must be [N,K] with K padded to group_size")
    rows, padded_k = weights.shape
    groups = padded_k // group_size
    view = weights.reshape(rows, groups, group_size)
    scales = np.max(np.abs(view), axis=2).astype(np.float32) / np.float32(7.0)
    scales[scales == 0] = np.float32(1.0)
    quantized = np.rint(view / scales[:, :, None]).clip(-8, 7).astype(np.int8)
    return quantized.reshape(rows, padded_k), scales


def quantize_activation(activation: np.ndarray) -> tuple[np.ndarray, np.float32]:
    """Symmetric INT8 quantization for one activation vector."""
    if activation.ndim != 1 or activation.size == 0:
        raise ValueError("activation must be a non-empty vector")
    scale = np.float32(np.max(np.abs(activation)) / 127.0)
    if scale == 0:
        scale = np.float32(1.0)
    quantized = np.rint(activation / scale).clip(-128, 127).astype(np.int8)
    return quantized, scale


def write_model_slice(
    output_dir: Path,
    weights: np.ndarray,
    activation: np.ndarray,
    metadata: dict[str, Any],
    group_size: int = 128,
) -> dict[str, Any]:
    """Quantize a floating-point slice and write the v1 fixture files."""
    if weights.ndim != 2 or activation.ndim != 1 or weights.shape[1] != activation.size:
        raise ValueError("weights and activation shapes do not match")
    rows, logical_k = weights.shape
    padded_k = ((logical_k + group_size - 1) // group_size) * group_size
    padded_weights = np.zeros((rows, padded_k), dtype=np.float32)
    padded_weights[:, :logical_k] = weights
    padded_activation = np.zeros((padded_k,), dtype=np.float32)
    padded_activation[:logical_k] = activation
    q_weights, weight_scales = quantize_weights_groupwise(padded_weights, group_size)
    q_activation, activation_scale = quantize_activation(padded_activation)
    logical_weights = q_weights[:, :logical_k].astype(np.int16).tolist()
    logical_activation = q_activation[:logical_k].astype(np.int16).tolist()
    expected = np.asarray(gemv_partial_sums(logical_weights, logical_activation, group_size), dtype=np.int32)
    output_dir.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = {
        "format_version": 1,
        "source": "real_model_slice",
        "N": rows,
        "K": logical_k,
        "padded_K": padded_k,
        "lanes": 32,
        "group_size": group_size,
        "quantization": "symmetric_w4a8",
        "weight_scale_layout": "[N,ceil(K/group_size)]",
        "activation_scale_layout": "one scalar",
        **metadata,
    }
    (output_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (output_dir / "weight_packed.bin").write_bytes(
        pack_weight_matrix(q_weights.astype(np.int16).tolist(), group_size)
    )
    (output_dir / "activation_int8.bin").write_bytes(q_activation.tobytes())
    np.save(output_dir / "scales.npy", weight_scales.astype(np.float32))
    np.save(output_dir / "activation_scale.npy", np.asarray(activation_scale, dtype=np.float32))
    np.save(output_dir / "expected_partial.npy", expected)
    stream = list(iter_gemv_beats(logical_weights, logical_activation, 32, group_size))
    (output_dir / "stream_reference.json").write_text(json.dumps(stream, indent=2) + "\n", encoding="utf-8")
    return config
