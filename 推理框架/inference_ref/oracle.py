"""Independent NumPy arithmetic; no calls to the scalar reference."""

import numpy as np

from .contracts import checked_output, validate_inputs


def execute(op: str, inputs: dict[str, np.ndarray]) -> np.ndarray:
    dtype, shape = validate_inputs(op, inputs)
    work_type = object if dtype.name == "int32" else np.float64
    arrays = {name: value.astype(work_type) for name, value in inputs.items()}
    if op == "linear":
        result = arrays["weight"] @ arrays["input"]
        if "bias" in arrays:
            result = result + arrays["bias"]
    elif op == "add":
        result = arrays["a"] + arrays["b"]
    else:
        result = np.maximum(arrays["input"], 0)
    return checked_output(result, dtype, shape)
