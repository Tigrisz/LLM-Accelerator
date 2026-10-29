"""Strict, data-only model-package-v1. No executable code or model dependency."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

import numpy as np
from .platform import resolve_platform

from .contracts import ContractError, DTYPES, MAX_DATA_BYTES, TensorSpec, require

MAX_MANIFEST = 1024 * 1024
MAX_TENSORS = 4096
MAX_NODES = 1024
ALIGNMENT = 64
FORMAT = "inference-model-package"
ROLES = {"constant", "input", "intermediate", "output"}
BINDINGS = {"linear": ({"weight", "input"}, {"weight", "input", "bias"}),
            "add": ({"a", "b"},), "relu": ({"input"},)}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _root(path) -> Path:
    try:
        candidate = Path(path)
        if "\0" in str(candidate):
            raise ValueError("Embedded null character in package path")
        return candidate.resolve()
    except (TypeError, ValueError) as exc:
        raise ContractError("INVALID_ARGUMENT", str(exc)) from exc
    except (OSError, RuntimeError) as exc:
        raise ContractError("IO_ERROR", str(exc)) from exc


def align_up(size: int, alignment: int) -> int:
    return (size + alignment - 1) // alignment * alignment


def _keys(value, expected: set, where: str) -> None:
    require(isinstance(value, dict) and set(value) == expected,
            "INVALID_MODEL", f"{where}: missing or unknown fields")


def _identifier(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", value) is not None


def _integer(value, maximum=2**64-1) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _hash(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True)
class TensorRecord:
    id: str
    role: str
    spec: TensorSpec
    offset: int = 0
    length: int = 0
    sha256: str = ""


@dataclass(frozen=True)
class Node:
    id: str
    op: str
    inputs: tuple[tuple[str, str], ...]
    output: str


@dataclass(frozen=True)
class ModelPackage:
    model_id: str
    tensors: tuple[TensorRecord, ...]
    nodes: tuple[Node, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    weights: bytes
    manifest_sha256: str
    weights_sha256: str

    def tensor(self, name: str) -> TensorRecord:
        found = next((t for t in self.tensors if t.id == name), None)
        require(found is not None, "INVALID_ARGUMENT", f"Unknown tensor {name}")
        return found

    def constant_array(self, name: str) -> np.ndarray:
        t = self.tensor(name)
        require(t.role == "constant", "INVALID_ARGUMENT", "Not a constant")
        return np.frombuffer(self.weights, DTYPES[t.spec.dtype], count=t.length//4,
                             offset=t.offset).reshape(t.spec.storage_shape)


def _header(m):
    _keys(m, {"format", "version", "model_id", "tensors", "nodes", "inputs", "outputs", "weights"}, "manifest")
    require(m["format"] == FORMAT and type(m["version"]) is int and m["version"] == 1,
            "UNSUPPORTED", "Unsupported model package format/version")
    require(_identifier(m["model_id"]), "INVALID_MODEL", "Invalid model_id")
    w = m["weights"]
    _keys(w, {"file", "byte_length", "sha256"}, "weights")
    require(w["file"] == "weights.bin", "INVALID_MODEL", "Only fixed weights.bin is allowed")
    require(_integer(w["byte_length"]), "INVALID_MODEL", "Invalid weights length")
    require(w["byte_length"] <= MAX_DATA_BYTES, "RESOURCE_LIMIT", "Weights exceed 16MiB")
    require(_hash(w["sha256"]), "INVALID_MODEL", "Invalid weights checksum")


def _validate(m: dict, data: bytes, manifest_hash: str) -> ModelPackage:
    _header(m)
    require(len(data) == m["weights"]["byte_length"], "INVALID_MODEL", "Weights length mismatch")
    require(digest(data) == m["weights"]["sha256"], "CHECKSUM_MISMATCH", "Weights checksum mismatch")
    require(isinstance(m["tensors"], list) and 1 <= len(m["tensors"]) <= MAX_TENSORS,
            "RESOURCE_LIMIT", "Need 1..4096 tensors")
    require(isinstance(m["nodes"], list) and 1 <= len(m["nodes"]) <= MAX_NODES,
            "RESOURCE_LIMIT", "Need 1..1024 nodes")
    tensors, names, sections = [], {}, []
    for item in m["tensors"]:
        require(isinstance(item, dict) and isinstance(item.get("role"), str) and item["role"] in ROLES,
                "INVALID_MODEL", "Unknown tensor role")
        constant = item["role"] == "constant"
        _keys(item, {"id", "role", "dtype", "layout", "shape", "storage_shape"} |
              ({"blob"} if constant else set()), "tensor")
        require(_identifier(item["id"]) and item["id"] not in names, "INVALID_MODEL", "Invalid/duplicate tensor ID")
        require(isinstance(item["shape"], list) and isinstance(item["storage_shape"], list),
                "INVALID_SHAPE", "Shape fields must be arrays")
        spec = TensorSpec(item["dtype"], tuple(item["shape"]), tuple(item["storage_shape"]), item["layout"])
        offset, length, checksum = 0, 0, ""
        if constant:
            blob = item["blob"]
            _keys(blob, {"offset", "length", "sha256"}, "constant blob")
            offset, length, checksum = blob["offset"], blob["length"], blob["sha256"]
            require(_integer(offset) and _integer(length) and offset % ALIGNMENT == 0 and
                    length == spec.byte_length and offset <= len(data) and length <= len(data)-offset,
                    "INVALID_MODEL", "Invalid constant offset/length/alignment")
            require(_hash(checksum), "INVALID_MODEL", "Invalid constant checksum")
            require(digest(data[offset:offset+length]) == checksum,
                    "CHECKSUM_MISMATCH", f"Constant checksum mismatch: {item['id']}")
            sections.append((offset, offset+length))
            array = np.frombuffer(data, DTYPES[spec.dtype], count=length//4, offset=offset).reshape(spec.storage_shape)
            require(bool(np.isfinite(array).all()), "NONFINITE", "Nonfinite constant")
            for axis, logical in enumerate(spec.shape):
                tail = [slice(None)] * len(spec.shape)
                tail[axis] = slice(logical, None)
                require(bool((array[tuple(tail)] == 0).all()), "INVALID_MODEL", "Nonzero constant padding")
        t = TensorRecord(item["id"], item["role"], spec, offset, length, checksum)
        tensors.append(t)
        names[t.id] = t
    cursor = 0
    for start, end in sorted(sections):
        require(start == align_up(cursor, ALIGNMENT) and not any(data[cursor:start]),
                "INVALID_MODEL", "Overlapping/noncanonical blobs or nonzero alignment gap")
        cursor = end
    require(cursor == len(data), "INVALID_MODEL", "Unexpected trailing/unreferenced weight data")
    for field, role in (("inputs", "input"), ("outputs", "output")):
        values = m[field]
        require(isinstance(values, list) and values and all(_identifier(v) for v in values) and
                len(values) == len(set(values)) and set(values) == {t.id for t in tensors if t.role == role},
                "INVALID_MODEL", f"Declared {field} must match tensor roles")
    available = {t.id for t in tensors if t.role in {"input", "constant"}}
    node_ids, nodes, consumed = set(), [], set()
    for item in m["nodes"]:
        _keys(item, {"id", "op", "inputs", "output"}, "node")
        require(_identifier(item["id"]) and item["id"] not in node_ids, "INVALID_MODEL", "Invalid/duplicate node ID")
        node_ids.add(item["id"])
        op, bound, output = item["op"], item["inputs"], item["output"]
        require(isinstance(op, str) and op in BINDINGS, "UNSUPPORTED", "Unsupported operator")
        require(isinstance(bound, dict) and set(bound) in BINDINGS[op] and
                all(isinstance(v, str) and v in available for v in bound.values()),
                "INVALID_MODEL", "Bad binding, missing tensor or forward reference")
        require(isinstance(output, str) and output in names and output not in available and
                names[output].role in {"intermediate", "output"}, "INVALID_MODEL", "Invalid output writer")
        inputs = {k: names[v].spec for k, v in bound.items()}
        first = next(iter(inputs.values()))
        require(all(t.dtype == first.dtype for t in inputs.values()) and names[output].spec.dtype == first.dtype,
                "INVALID_MODEL", "Mixed dtype in node")
        if op == "linear":
            w, x = inputs["weight"], inputs["input"]
            require(len(w.shape) == 2 and len(x.shape) == 1 and w.shape[1] == x.shape[0],
                    "INVALID_SHAPE", "linear requires W[N,K], x[K]")
            shape = (w.shape[0],)
            require("bias" not in inputs or inputs["bias"].shape == shape, "INVALID_SHAPE", "Bad bias shape")
        else:
            shape = first.shape
            require(all(t.shape == shape for t in inputs.values()), "INVALID_SHAPE", "Broadcast is unsupported")
        require(names[output].spec.shape == shape, "INVALID_SHAPE", "Node output shape mismatch")
        available.add(output)
        consumed.update(bound.values())
        nodes.append(Node(item["id"], op, tuple(sorted(bound.items())), output))
    require(available == set(names), "INVALID_MODEL", "Unproduced tensor")
    require(consumed | set(m["outputs"]) == set(names), "INVALID_MODEL", "Unused tensor")
    return ModelPackage(m["model_id"], tuple(tensors), tuple(nodes), tuple(m["inputs"]),
                        tuple(m["outputs"]), data, manifest_hash, digest(data))


def _read_file(root: Path, name: str, limit: int,platform,trace=None) -> bytes:
    path = root / name
    try:
        require(not path.is_symlink() and path.resolve().parent == root,
                "INVALID_MODEL", "Package file must be local, not a symlink")
        require(path.is_file(), "IO_ERROR", "Package entry must be a regular file")
        content=platform.read_blob(path,limit,trace=trace)
    except OSError as exc:
        raise ContractError("IO_ERROR", str(exc)) from exc
    require(len(content) <= limit, "RESOURCE_LIMIT", f"{name} exceeds limit")
    return content


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "INVALID_MODEL", "Duplicate JSON key")
        result[key] = value
    return result


def read_package(path: Path,*,platform=None,trace=None) -> ModelPackage:
    platform=resolve_platform(platform)
    root = _root(path)
    raw = _read_file(root, "manifest.json", MAX_MANIFEST,platform,trace)
    try:
        def invalid_constant(value):
            raise ContractError("INVALID_MODEL", f"Nonstandard JSON number {value}")
        metadata = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                              parse_constant=invalid_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("INVALID_MODEL", str(exc)) from exc
    _header(metadata)
    data = _read_file(root, "weights.bin", MAX_DATA_BYTES,platform,trace)
    return _validate(metadata, data, digest(raw))


def write_package(path: Path, *, model_id: str, tensors: list, nodes: list,
                  inputs: list, outputs: list, constants: dict[str, np.ndarray]) -> None:
    """Offline writer: logical constant arrays -> zero-padded, little-endian storage."""
    root = _root(path)
    require(isinstance(tensors, list) and isinstance(constants, dict), "INVALID_ARGUMENT", "Invalid writer inputs")
    require(len(tensors) <= MAX_TENSORS, "RESOURCE_LIMIT", "Too many tensors")
    try:
        records = json.loads(json.dumps(tensors, allow_nan=False))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ContractError("INVALID_MODEL", str(exc)) from exc
    data, expected_constants = bytearray(), set()
    for record in records:
        require(isinstance(record, dict), "INVALID_MODEL", "Invalid tensor record")
        if record.get("role") != "constant":
            continue
        _keys(record, {"id", "role", "dtype", "shape", "storage_shape", "layout"}, "writer tensor")
        require(_identifier(record["id"]), "INVALID_MODEL", "Invalid constant ID")
        require(isinstance(record["shape"], list) and isinstance(record["storage_shape"], list),
                "INVALID_SHAPE", "Shape must be arrays")
        spec = TensorSpec(record["dtype"], tuple(record["shape"]), tuple(record["storage_shape"]), record["layout"])
        expected_constants.add(record["id"])
        array = constants.get(record["id"])
        require(isinstance(array, np.ndarray) and array.dtype == np.dtype(spec.dtype) and array.shape == spec.shape,
                "INVALID_ARGUMENT", "Constant must have exact logical shape and native dtype")
        offset = align_up(len(data), ALIGNMENT)
        require(offset + spec.byte_length <= MAX_DATA_BYTES, "RESOURCE_LIMIT", "Weights exceed limit")
        storage = np.zeros(spec.storage_shape, DTYPES[spec.dtype])
        storage[tuple(slice(0, n) for n in spec.shape)] = array
        raw = storage.tobytes(order="C")
        data.extend(b"\0" * (offset-len(data)))
        data.extend(raw)
        record["blob"] = {"offset": offset, "length": len(raw), "sha256": digest(raw)}
    require(set(constants) == expected_constants, "INVALID_ARGUMENT", "Constant bindings mismatch")
    metadata = {"format": FORMAT, "version": 1, "model_id": model_id,
                "tensors": records, "nodes": nodes, "inputs": inputs, "outputs": outputs,
                "weights": {"file": "weights.bin", "byte_length": len(data), "sha256": digest(data)}}
    _validate(metadata, bytes(data), "")
    try:
        raw = (json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")
        require(len(raw) <= MAX_MANIFEST, "RESOURCE_LIMIT", "Manifest exceeds limit")
        root.mkdir(parents=True, exist_ok=False)
        with (root / "weights.bin").open("xb") as stream:
            stream.write(data)
        with (root / "manifest.json").open("xb") as stream:
            stream.write(raw)
    except FileExistsError as exc:
        raise ContractError("ALREADY_EXISTS", str(exc)) from exc
    except OSError as exc:
        raise ContractError("IO_ERROR", str(exc)) from exc
