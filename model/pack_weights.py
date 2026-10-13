"""Signed INT4 packing helpers used by the RTL contract.

Packing is little-nibble first: element 0 is bits [3:0], element 1 is
bits [7:4], and so on. The helpers intentionally use Python integers so
they are also usable without NumPy in small smoke tests.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence


def _check_int4(value: int) -> int:
    value = int(value)
    if value < -8 or value > 7:
        raise ValueError(f"INT4 value out of range: {value}")
    return value


def decode_int4(nibble: int) -> int:
    """Decode a 4-bit two's-complement nibble."""
    nibble = int(nibble) & 0xF
    return nibble - 16 if nibble & 0x8 else nibble


def pack_int4(values: Iterable[int]) -> bytes:
    """Pack signed INT4 values, two values per byte.

    An odd number of values is padded with a zero high nibble. The caller
    should carry the valid element count separately when this padding is
    semantically significant.
    """
    vals = [_check_int4(v) for v in values]
    out = bytearray((len(vals) + 1) // 2)
    for index, value in enumerate(vals):
        nibble = value & 0xF
        if index & 1:
            out[index // 2] |= nibble << 4
        else:
            out[index // 2] = nibble
    return bytes(out)


def unpack_int4(data: bytes, count: int | None = None) -> List[int]:
    """Unpack little-nibble-first signed INT4 values."""
    values: List[int] = []
    for byte in data:
        values.append(decode_int4(byte & 0xF))
        values.append(decode_int4((byte >> 4) & 0xF))
    return values if count is None else values[:count]


def pack_weight_matrix(weights: Sequence[Sequence[int]], group_size: int = 128) -> bytes:
    """Pack a row-major matrix, zero-padding each row to a group boundary."""
    if group_size <= 0:
        raise ValueError("group_size must be positive")
    rows = [list(row) for row in weights]
    if not rows:
        return b""
    width = len(rows[0])
    if width == 0 or any(len(row) != width for row in rows):
        raise ValueError("weights must be a non-empty rectangular matrix")
    padded_width = ((width + group_size - 1) // group_size) * group_size
    flat: List[int] = []
    for row in rows:
        checked = [_check_int4(v) for v in row]
        flat.extend(checked)
        flat.extend([0] * (padded_width - width))
    return pack_int4(flat)


def unpack_weight_matrix(data: bytes, rows: int, cols: int, group_size: int = 128) -> List[List[int]]:
    """Inverse of :func:`pack_weight_matrix` for valid elements."""
    if rows < 0 or cols < 0 or group_size <= 0:
        raise ValueError("rows, cols, and group_size must be non-negative/positive")
    padded_width = ((cols + group_size - 1) // group_size) * group_size if cols else 0
    needed = rows * padded_width
    values = unpack_int4(data, needed)
    if len(values) != needed:
        raise ValueError(f"packed data is too short: need {needed} values, got {len(values)}")
    return [values[r * padded_width : r * padded_width + cols] for r in range(rows)]

