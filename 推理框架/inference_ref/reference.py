"""Scalar reference: math.fsum over FP64, exact Python integers for INT32."""

import math

import numpy as np

from .contracts import checked_output, validate_inputs


def execute(op: str, inputs: dict[str, np.ndarray]) -> np.ndarray:
    dtype, shape = validate_inputs(op, inputs)
    cast = int if dtype.name == "int32" else float
    values = []
    if op == "linear":
        w, x = inputs["weight"], inputs["input"]
        for row in range(w.shape[0]):
            products = [cast(w[row, col]) * cast(x[col]) for col in range(w.shape[1])]
            if "bias" in inputs:
                products.append(cast(inputs["bias"][row]))
            values.append(sum(products) if dtype.name == "int32" else math.fsum(products))
    elif op == "add":
        values = [cast(a) + cast(b) for a, b in zip(inputs["a"].flat, inputs["b"].flat)]
    else:
        values = [max(cast(a), 0) for a in inputs["input"].flat]
    return checked_output(values, dtype, shape)
