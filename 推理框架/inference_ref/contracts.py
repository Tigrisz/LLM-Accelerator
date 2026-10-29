"""Executable subset of the contracts described in docs/contracts.md."""

from dataclasses import dataclass
from math import prod
import math
from numbers import Real

import numpy as np

MAX_ELEMENTS = 1_048_576
MAX_DATA_BYTES = 16 * 1024 * 1024
DTYPES = {"float32": np.dtype("<f4"), "int32": np.dtype("<i4")}


class ContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise ContractError(code, message)


def valid_tolerance(value) -> bool:
    if not isinstance(value, Real) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value)) and value >= 0
    except (ValueError, OverflowError):
        return False


@dataclass(frozen=True)
class TensorSpec:
    dtype: str
    shape: tuple[int, ...]
    storage_shape: tuple[int, ...]
    layout: str = "row_major"

    def __post_init__(self):
        require(isinstance(self.dtype, str) and self.dtype in DTYPES,
                "UNSUPPORTED", "Only float32/int32 storage is implemented")
        require(self.layout == "row_major", "UNSUPPORTED", "Unknown tensor layout")
        for dims in (self.shape, self.storage_shape):
            require(isinstance(dims, (tuple, list)) and 1 <= len(dims) <= 4,
                    "INVALID_SHAPE", "Tensor rank must be 1..4")
            require(all(type(d) is int and d > 0 for d in dims),
                    "INVALID_SHAPE", "Dimensions must be positive integers")
        require(len(self.shape) == len(self.storage_shape),
                "INVALID_SHAPE", "Logical and storage ranks differ")
        require(all(a <= b for a, b in zip(self.shape, self.storage_shape)),
                "INVALID_SHAPE", "Logical shape exceeds storage")
        require(prod(self.storage_shape) <= MAX_ELEMENTS,
                "RESOURCE_LIMIT", "Tensor exceeds phase-1A element limit")

    @property
    def byte_length(self) -> int:
        return prod(self.storage_shape) * DTYPES[self.dtype].itemsize


def validate_inputs(op: str, inputs: dict[str, np.ndarray]) -> tuple[np.dtype, tuple]:
    allowed = {"linear": ({"weight", "input"}, {"weight", "input", "bias"}),
               "add": ({"a", "b"},), "relu": ({"input"},)}
    require(isinstance(op, str) and op in allowed, "UNSUPPORTED", "Unknown operator")
    require(isinstance(inputs, dict) and set(inputs) in allowed[op],
            "INVALID_ARGUMENT", "Wrong operator input names")
    dtype = None
    for name, array in inputs.items():
        require(isinstance(array, np.ndarray), "INVALID_ARGUMENT", f"{name}: expected ndarray")
        TensorSpec(array.dtype.name, tuple(array.shape), tuple(array.shape))
        require(dtype is None or array.dtype == dtype,
                "INVALID_ARGUMENT", "Mixed input dtypes are not allowed")
        dtype = array.dtype
        require(bool(np.isfinite(array).all()), "NONFINITE", f"{name}: nonfinite input")
    if op == "linear":
        w, x = inputs["weight"], inputs["input"]
        require(w.ndim == 2 and x.ndim == 1 and w.shape[1] == x.shape[0],
                "INVALID_SHAPE", "linear requires W[N,K] and x[K]")
        shape = (w.shape[0],)
        require("bias" not in inputs or inputs["bias"].shape == shape,
                "INVALID_SHAPE", "bias must have shape [N]")
    elif op == "add":
        require(inputs["a"].shape == inputs["b"].shape,
                "INVALID_SHAPE", "add does not broadcast")
        shape = inputs["a"].shape
    else:
        shape = inputs["input"].shape
    return dtype, shape


def checked_output(values, dtype: np.dtype, shape: tuple) -> np.ndarray:
    """Only validation/conversion is shared; arithmetic paths stay independent."""
    if dtype.name == "int32":
        flat = np.asarray(values, dtype=object).reshape(-1)
        require(all(-(1 << 31) <= int(v) < (1 << 31) for v in flat),
                "NUMERIC_OVERFLOW", "Final INT32 result is out of range")
    else:
        array = np.asarray(values, dtype=np.float64)
        require(bool(np.isfinite(array).all()),
                "NUMERIC_OVERFLOW", "Nonfinite FP64 intermediate result")
        with np.errstate(over="ignore", invalid="ignore"):
            rounded = array.astype(dtype)
        require(bool(np.isfinite(rounded).all()),
                "NUMERIC_OVERFLOW", "Result cannot be represented as finite FP32")
        return rounded.reshape(shape)
    return np.asarray(values, dtype=dtype).reshape(shape)
