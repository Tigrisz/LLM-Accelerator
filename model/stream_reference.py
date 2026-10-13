"""Reference beat generator for the task A compute-core integration."""

from __future__ import annotations

from typing import Dict, Iterator, Sequence

try:
    from .golden_gemv import stream_metadata
    from .pack_weights import pack_int4
except ImportError:  # direct script execution
    from golden_gemv import stream_metadata
    from pack_weights import pack_int4


def _signed_bytes(values: Sequence[int]) -> bytes:
    return bytes((int(value) & 0xFF) for value in values)


def iter_gemv_beats(
    weights: Sequence[Sequence[int]],
    activation: Sequence[int],
    lanes: int = 32,
    group_size: int = 128,
) -> Iterator[Dict[str, object]]:
    """Yield the exact paired weight/activation beats expected by ``gemv_core``.

    The activation vector is deliberately repeated for each output row. A
    future RTL integration should obtain those repeated beats from
    ``activation_cache`` rather than rereading DDR.
    """
    rows = len(weights)
    if rows == 0 or not activation:
        raise ValueError("weights and activation must be non-empty")
    cols = len(activation)
    if any(len(row) != cols for row in weights):
        raise ValueError("weights must be rectangular")
    if group_size % lanes:
        raise ValueError("group_size must be a multiple of lanes")
    padded_cols = ((cols + group_size - 1) // group_size) * group_size
    padded_activation = list(activation) + [0] * (padded_cols - cols)

    metadata = stream_metadata(rows, cols, lanes, group_size)
    for item in metadata:
        row = int(item["row_id"])
        group = int(item["group_id"])
        beat = int(item["beat_id"])
        start = group * group_size + beat * lanes
        weight_values = list(weights[row][start : min(start + lanes, cols)])
        weight_values += [0] * (lanes - len(weight_values))
        activation_values = padded_activation[start : start + lanes]
        activation_values += [0] * (lanes - len(activation_values))
        yield {
            **item,
            "weight_data_hex": pack_int4(weight_values).hex(),
            "activation_data_hex": _signed_bytes(activation_values).hex(),
        }

