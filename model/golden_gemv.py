"""Bit-exact integer reference for the W4A8 GEMV stream."""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple


def _validate_matrix(weights: Sequence[Sequence[int]], activation: Sequence[int]) -> Tuple[int, int]:
    rows = len(weights)
    if rows == 0:
        raise ValueError("weights must have at least one row")
    cols = len(weights[0])
    if cols == 0 or any(len(row) != cols for row in weights):
        raise ValueError("weights must be a non-empty rectangular matrix")
    if len(activation) != cols:
        raise ValueError(f"activation length {len(activation)} does not match K={cols}")
    return rows, cols


def _check_range(values: Iterable[int], low: int, high: int, name: str) -> None:
    for value in values:
        value = int(value)
        if value < low or value > high:
            raise ValueError(f"{name} value out of range: {value}")


def gemv_partial_sums(
    weights: Sequence[Sequence[int]],
    activation: Sequence[int],
    group_size: int = 128,
) -> List[List[int]]:
    """Return signed INT32 partial sums with shape [N, ceil(K/group_size)]."""
    rows, cols = _validate_matrix(weights, activation)
    if group_size <= 0:
        raise ValueError("group_size must be positive")
    _check_range((v for row in weights for v in row), -8, 7, "weight INT4")
    _check_range(activation, -128, 127, "activation INT8")
    groups = math.ceil(cols / group_size)
    result: List[List[int]] = []
    for row in weights:
        row_result: List[int] = []
        for group in range(groups):
            start = group * group_size
            stop = min(start + group_size, cols)
            total = sum(int(row[k]) * int(activation[k]) for k in range(start, stop))
            if total < -(1 << 31) or total > (1 << 31) - 1:
                raise OverflowError("partial sum does not fit signed INT32")
            row_result.append(total)
        result.append(row_result)
    return result


def stream_metadata(rows: int, cols: int, lanes: int = 32, group_size: int = 128) -> List[dict]:
    """Describe the expected weight/activation beat sequence for RTL tests."""
    if rows <= 0 or cols <= 0 or lanes <= 0 or group_size <= 0:
        raise ValueError("rows, cols, lanes, and group_size must be positive")
    if group_size % lanes:
        raise ValueError("v1 requires group_size to be a multiple of lanes")
    groups = math.ceil(cols / group_size)
    beats_per_group = math.ceil(group_size / lanes)
    metadata: List[dict] = []
    for row in range(rows):
        for group in range(groups):
            for beat in range(beats_per_group):
                valid_in_group = min(lanes, max(0, cols - group * group_size - beat * lanes))
                metadata.append(
                    {
                        "row_id": row,
                        "group_id": group,
                        "beat_id": beat,
                        "group_first": beat == 0,
                        "group_last": beat == beats_per_group - 1,
                        "valid_elements": valid_in_group,
                    }
                )
    return metadata

