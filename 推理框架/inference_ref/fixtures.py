"""fixture-v1: bounded JSON metadata plus checksummed little-endian data."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

import numpy as np

from .contracts import (ContractError, DTYPES, MAX_DATA_BYTES, TensorSpec,
                        require, validate_inputs, valid_tolerance)

ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
MAX_MANIFEST_BYTES = 1024 * 1024


def _keys(value, expected, context):
    require(isinstance(value, dict) and set(value) == set(expected),
            "INVALID_FIXTURE", f"{context}: missing or unknown fields")


def _uint(value, context):
    require(type(value) is int and 0 <= value < (1 << 64),
            "INVALID_FIXTURE", f"{context}: expected uint64")


def _hash(value, context):
    require(isinstance(value, str) and SHA.fullmatch(value) is not None,
            "INVALID_FIXTURE", f"{context}: invalid SHA-256")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "INVALID_FIXTURE", f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ContractError("INVALID_FIXTURE", f"Nonfinite JSON value: {value}")


def read_json(path: Path):
    try:
        require(path.is_file() and not path.is_symlink(),
                "IO_ERROR", f"Not a regular metadata file: {path}")
        require(path.stat().st_size <= MAX_MANIFEST_BYTES,
                "RESOURCE_LIMIT", "Metadata is too large")
        return json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=_pairs, parse_constant=_constant)
    except (OSError, UnicodeError) as exc:
        raise ContractError("IO_ERROR", str(exc)) from exc
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("INVALID_FIXTURE", str(exc)) from exc


@dataclass(frozen=True)
class Fixture:
    metadata: dict
    inputs: dict[str, np.ndarray]
    expected: np.ndarray


def _validate(meta, data: bytes) -> Fixture:
    _keys(meta, ("format", "version", "case_id", "provenance", "operation",
                 "comparison", "payload", "tensors"), "manifest")
    require(meta["format"] == "inference-fixture" and type(meta["version"]) is int
            and meta["version"] == 1, "UNSUPPORTED", "Unsupported fixture format/version")
    require(isinstance(meta["case_id"], str) and ID.fullmatch(meta["case_id"]) is not None,
            "INVALID_FIXTURE", "Invalid case_id")
    source = meta["provenance"]
    _keys(source, ("kind", "source", "seed"), "provenance")
    require(isinstance(source["kind"], str) and
            source["kind"] in ("manual", "synthetic", "external_reference"),
            "INVALID_FIXTURE", "Invalid provenance kind")
    require(isinstance(source["source"], str) and 0 < len(source["source"]) <= 512,
            "INVALID_FIXTURE", "Provenance source must be a nonempty string")
    if source["seed"] is not None:
        _uint(source["seed"], "seed")
    payload = meta["payload"]
    _keys(payload, ("file", "byte_length", "sha256"), "payload")
    require(payload["file"] == "data.bin", "INVALID_FIXTURE", "Payload must be data.bin")
    _uint(payload["byte_length"], "payload byte_length")
    require(payload["byte_length"] == len(data) <= MAX_DATA_BYTES,
            "INVALID_FIXTURE", "Payload length mismatch or limit exceeded")
    _hash(payload["sha256"], "payload")
    require(hashlib.sha256(data).hexdigest() == payload["sha256"],
            "CHECKSUM_MISMATCH", "Payload SHA-256 mismatch")
    tensors = meta["tensors"]
    require(isinstance(tensors, list) and 2 <= len(tensors) <= 4,
            "INVALID_FIXTURE", "Expected two to four tensor records")
    arrays, records, ranges = {}, {}, []
    for item in tensors:
        _keys(item, ("name", "dtype", "shape", "storage_shape", "layout", "role",
                     "offset", "byte_length", "alignment", "sha256"), "tensor")
        name = item["name"]
        require(isinstance(name, str) and ID.fullmatch(name) is not None and name not in arrays,
                "INVALID_FIXTURE", "Invalid or duplicated tensor name")
        require(isinstance(item["shape"], list) and isinstance(item["storage_shape"], list),
                "INVALID_FIXTURE", "Shapes must be JSON arrays")
        spec = TensorSpec(item["dtype"], item["shape"], item["storage_shape"], item["layout"])
        _uint(item["offset"], "tensor offset")
        _uint(item["byte_length"], "tensor byte_length")
        require(type(item["alignment"]) is int and item["alignment"] == 4 and
                item["offset"] % 4 == 0 and item["byte_length"] == spec.byte_length,
                "INVALID_FIXTURE", "Alignment or tensor byte length mismatch")
        end = item["offset"] + item["byte_length"]
        require(end <= len(data), "INVALID_FIXTURE", "Tensor is outside payload")
        require(item["role"] in ("input", "reference"),
                "INVALID_FIXTURE", "Invalid tensor role")
        chunk = data[item["offset"]:end]
        _hash(item["sha256"], "tensor")
        require(hashlib.sha256(chunk).hexdigest() == item["sha256"],
                "CHECKSUM_MISMATCH", f"{name}: SHA-256 mismatch")
        storage = np.frombuffer(chunk, dtype=DTYPES[spec.dtype]).reshape(spec.storage_shape)
        require(bool(np.isfinite(storage).all()), "NONFINITE", f"{name}: nonfinite data")
        slices = tuple(slice(0, size) for size in spec.shape)
        padding = storage.copy()
        padding[slices] = 0
        require(not bool(np.any(padding != 0)), "INVALID_FIXTURE", f"{name}: nonzero padding")
        logical = storage[slices].copy()
        logical.setflags(write=False)
        arrays[name], records[name] = logical, item
        ranges.append((item["offset"], end))
    cursor = 0
    for start, end in sorted(ranges):
        require(start == cursor, "INVALID_FIXTURE", "Overlapping tensors or uncovered bytes")
        cursor = end
    require(cursor == len(data), "INVALID_FIXTURE", "Uncovered payload tail")
    operation = meta["operation"]
    _keys(operation, ("name", "inputs", "output", "attributes"), "operation")
    names = operation["inputs"]
    require(isinstance(names, list) and all(isinstance(n, str) for n in names)
            and len(names) == len(set(names)), "INVALID_FIXTURE", "Invalid input references")
    require(operation["output"] == "expected" and operation["attributes"] == {},
            "UNSUPPORTED", "Only expected output and empty attributes are supported")
    require(set(names) | {"expected"} == set(arrays) and "expected" not in names,
            "INVALID_FIXTURE", "Missing or unreferenced tensor")
    require(all(records[n]["role"] == "input" for n in names) and
            records["expected"]["role"] == "reference",
            "INVALID_FIXTURE", "Tensor role does not match operation")
    inputs = {name: arrays[name] for name in names}
    dtype, shape = validate_inputs(operation["name"], inputs)
    expected = arrays["expected"]
    require(expected.dtype == dtype and expected.shape == shape,
            "INVALID_SHAPE", "Expected output dtype/shape disagrees with operation")
    policy = meta["comparison"]
    _keys(policy, ("mode", "atol", "rtol"), "comparison")
    mode = "exact" if dtype.name == "int32" else "abs_plus_rel"
    require(policy["mode"] == mode, "INVALID_FIXTURE", "Invalid comparison mode")
    for value in (policy["atol"], policy["rtol"]):
        require(type(value) in (int, float) and valid_tolerance(value),
                "INVALID_FIXTURE", "Invalid comparison tolerance")
    require(mode != "exact" or (policy["atol"] == 0 and policy["rtol"] == 0),
            "INVALID_FIXTURE", "INT32 fixtures must use exact comparison")
    return Fixture(meta, inputs, expected)


def read_fixture(path: Path) -> Fixture:
    path = Path(path)
    meta = read_json(path / "manifest.json")
    try:
        data_path = path / "data.bin"
        require(data_path.is_file() and not data_path.is_symlink(),
                "IO_ERROR", "Payload is not a regular file")
        require(data_path.stat().st_size <= MAX_DATA_BYTES,
                "RESOURCE_LIMIT", "Payload exceeds phase-1A limit")
        data = data_path.read_bytes()
    except OSError as exc:
        raise ContractError("IO_ERROR", str(exc)) from exc
    return _validate(meta, data)


def write_fixture(path: Path, case_id: str, op: str, inputs: dict[str, np.ndarray],
                  expected: np.ndarray, *, provenance: dict,
                  storage_shapes: dict | None = None) -> None:
    dtype, shape = validate_inputs(op, inputs)
    require(isinstance(expected, np.ndarray) and expected.dtype == dtype and
            expected.shape == shape, "INVALID_SHAPE", "Wrong expected output")
    storage_shapes = {} if storage_shapes is None else storage_shapes
    require(isinstance(storage_shapes, dict) and set(storage_shapes) <= (set(inputs) | {"expected"}),
            "INVALID_ARGUMENT", "Unknown storage shape name")
    arrays = {**inputs, "expected": expected}
    records, chunks, cursor = [], [], 0
    for name in sorted(arrays):
        array = arrays[name]
        spec = TensorSpec(array.dtype.name, tuple(array.shape),
                          storage_shapes.get(name, tuple(array.shape)))
        require(cursor + spec.byte_length <= MAX_DATA_BYTES,
                "RESOURCE_LIMIT", "Payload exceeds phase-1A limit")
        storage = np.zeros(spec.storage_shape, dtype=DTYPES[spec.dtype])
        storage[tuple(slice(0, size) for size in spec.shape)] = array
        chunk = storage.tobytes(order="C")
        records.append({
            "name": name, "dtype": spec.dtype, "shape": list(spec.shape),
            "storage_shape": list(spec.storage_shape), "layout": spec.layout,
            "role": "reference" if name == "expected" else "input",
            "offset": cursor, "byte_length": len(chunk), "alignment": 4,
            "sha256": hashlib.sha256(chunk).hexdigest(),
        })
        chunks.append(chunk)
        cursor += len(chunk)
    data = b"".join(chunks)
    meta = {
        "format": "inference-fixture", "version": 1, "case_id": case_id,
        "provenance": provenance,
        "operation": {"name": op, "inputs": sorted(inputs), "output": "expected",
                      "attributes": {}},
        "comparison": {"mode": "exact" if dtype.name == "int32" else "abs_plus_rel",
                       "atol": 0 if dtype.name == "int32" else 1e-6,
                       "rtol": 0 if dtype.name == "int32" else 1e-5},
        "payload": {"file": "data.bin", "byte_length": len(data),
                    "sha256": hashlib.sha256(data).hexdigest()},
        "tensors": records,
    }
    _validate(meta, data)  # Complete validation before filesystem side effects.
    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=False)
        (path / "data.bin").write_bytes(data)
        (path / "manifest.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8", newline="\n")
    except FileExistsError as exc:
        raise ContractError("ALREADY_EXISTS", f"Refuse to overwrite {path}") from exc
    except OSError as exc:
        raise ContractError("IO_ERROR", str(exc)) from exc
