import numpy as np


def tensor(name, role, dtype, shape, storage=None):
    return {"id": name, "role": role, "dtype": dtype, "layout": "row_major",
            "shape": list(shape), "storage_shape": list(storage or shape)}


def chain_definition(dtype="int32", padded=False):
    tensors = [tensor("x", "input", dtype, (3,), (5,) if padded else None),
               tensor("w", "constant", dtype, (2, 3), (2, 5) if padded else None),
               tensor("bias", "constant", dtype, (2,)),
               tensor("delta", "constant", dtype, (2,)),
               tensor("w2", "constant", dtype, (2, 2))]
    tensors += [tensor(name, role, dtype, (2,), (4,) if padded else None)
                for name, role in (("h1", "intermediate"), ("h2", "intermediate"),
                                   ("h3", "intermediate"), ("y", "output"))]
    nodes = [{"id": "n0", "op": "linear", "inputs": {"weight": "w", "input": "x", "bias": "bias"}, "output": "h1"},
             {"id": "n1", "op": "relu", "inputs": {"input": "h1"}, "output": "h2"},
             {"id": "n2", "op": "add", "inputs": {"a": "h2", "b": "delta"}, "output": "h3"},
             {"id": "n3", "op": "linear", "inputs": {"weight": "w2", "input": "h3"}, "output": "y"}]
    constants = {"w": np.array([[1, -2, 3], [-4, 0, 2]], dtype),
                 "bias": np.array([1, -2], dtype), "delta": np.array([1, -1], dtype),
                 "w2": np.array([[1, 2], [-1, 3]], dtype)}
    return dict(model_id="synthetic_chain", tensors=tensors, nodes=nodes,
                inputs=["x"], outputs=["y"], constants=constants)
