"""Deterministic synthetic examples and independent three-way verification."""

import hashlib
import platform
from pathlib import Path

import numpy as np

from . import __version__, oracle, reference
from .compare import compare_arrays
from .contracts import ContractError, require
from .fixtures import ID, _hash, _keys, read_fixture, read_json, write_fixture


def _examples():
    for dtype, prefix in ((np.int32, "int"), (np.float32, "float")):
        values = {"weight": np.array([[1, -2, 3], [-4, 0, 2]], dtype),
                  "input": np.array([2, -3, 4], dtype),
                  "bias": np.array([1, -2], dtype)}
        yield prefix + "_hand_bias", "linear", values, np.array([21, -2], dtype), {}, None
        yield prefix + "_add", "add", {
            "a": np.array([[-2, 0, 4], [1, -3, 2]], dtype),
            "b": np.array([[1, 2, -1], [-1, 3, -4]], dtype),
        }, np.array([[-1, 2, 3], [0, 0, -2]], dtype), {}, None
        yield prefix + "_relu", "relu", {
            "input": np.array([-7, 0, 3], dtype)
        }, np.array([0, 0, 3], dtype), {}, None
    yield "float_cancellation", "linear", {
        "weight": np.array([[1e8, 1, -1e8]], np.float32),
        "input": np.ones(3, np.float32),
    }, np.array([1], np.float32), {}, None
    yield "int_cancellation", "linear", {
        "weight": np.array([[2**30, 2**30]], np.int32),
        "input": np.array([4, -4], np.int32),
    }, np.array([0], np.int32), {}, None
    yield "int_zero", "linear", {
        "weight": np.zeros((1, 5), np.int32), "input": np.ones(5, np.int32),
    }, np.zeros(1, np.int32), {}, None
    yield "float_single", "linear", {
        "weight": np.array([[1.5]], np.float32), "input": np.array([-2], np.float32),
    }, np.array([-3], np.float32), {}, None
    yield "float_padded", "linear", {
        "weight": np.arange(14, dtype=np.float32).reshape(2, 7) / np.float32(8),
        "input": np.arange(-3, 4, dtype=np.float32),
    }, None, {"weight": (2, 10), "input": (10,)}, None
    yield "int_padded", "linear", {
        "weight": np.arange(-20, 31, dtype=np.int32).reshape(3, 17),
        "input": np.arange(-8, 9, dtype=np.int32),
    }, None, {"weight": (3, 20), "input": (20,)}, None
    yield "int_extreme", "add", {
        "a": np.array([-2**31, 2**31 - 1], np.int32),
        "b": np.array([0, -1], np.int32),
    }, np.array([-2**31, 2**31 - 2], np.int32), {}, None
    yield "float_zero", "add", {
        "a": np.zeros((2, 3), np.float32), "b": np.zeros((2, 3), np.float32),
    }, np.zeros((2, 3), np.float32), {}, None
    for seed in range(20):
        rng = np.random.Generator(np.random.PCG64(seed))
        for dtype, prefix in ((np.int32, "int"), (np.float32, "float")):
            if dtype == np.int32:
                w = rng.integers(-31, 32, size=(3, 17), dtype=np.int32)
                x = rng.integers(-63, 64, size=17, dtype=np.int32)
            else:
                w = rng.normal(size=(5, 23)).astype(np.float32)
                x = rng.normal(size=23).astype(np.float32)
            yield f"{prefix}_random_{seed:02d}", "linear", {
                "weight": w, "input": x,
            }, None, {}, seed


def generate_suite(output: Path) -> dict:
    output = Path(output)
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ContractError("ALREADY_EXISTS", f"Refuse to overwrite {output}") from exc
    except OSError as exc:
        raise ContractError("IO_ERROR", str(exc)) from exc
    entries = []
    for name, op, inputs, literal, storage, seed in _examples():
        expected = reference.execute(op, inputs) if literal is None else literal
        write_fixture(
            output / name, name, op, inputs, expected, storage_shapes=storage,
            provenance={"kind": "synthetic" if seed is not None or literal is None else "manual",
                        "source": f"inference_ref.examples/v1; numpy={np.__version__}; PCG64",
                        "seed": seed},
        )
        entries.append({"directory": name, "manifest_sha256": hashlib.sha256(
            (output / name / "manifest.json").read_bytes()).hexdigest()})
    index = {"format": "inference-fixture-suite", "version": 1,
             "generator": f"inference_ref/{__version__}", "cases": entries}
    from .reporting import write_json_exclusive
    write_json_exclusive(output / "suite.json", index)
    return {"case_count": len(entries), "output": str(output.resolve())}


def verify_case(path: Path) -> dict:
    fixture = read_fixture(path)
    op = fixture.metadata["operation"]["name"]
    scalar = reference.execute(op, fixture.inputs)
    numpy_result = oracle.execute(op, fixture.inputs)
    policy = fixture.metadata["comparison"]
    comparisons = {
        "stored_vs_scalar": compare_arrays(fixture.expected, scalar, policy["atol"], policy["rtol"]),
        "stored_vs_numpy": compare_arrays(fixture.expected, numpy_result, policy["atol"], policy["rtol"]),
        "scalar_vs_numpy": compare_arrays(scalar, numpy_result, policy["atol"], policy["rtol"]),
    }
    return {"case_id": fixture.metadata["case_id"], "operation": op,
            "dtype": fixture.expected.dtype.name,
            "passed": all(report["passed"] for report in comparisons.values()),
            "comparisons": comparisons}


def verify_suite(root: Path) -> dict:
    root = Path(root).resolve()
    index_path = root / "suite.json"
    index = read_json(index_path)
    _keys(index, ("format", "version", "generator", "cases"), "suite")
    require(index["format"] == "inference-fixture-suite" and
            type(index["version"]) is int and index["version"] == 1,
            "UNSUPPORTED", "Unsupported suite format/version")
    require(isinstance(index["generator"], str) and bool(index["generator"]),
            "INVALID_FIXTURE", "Invalid generator name")
    entries = index["cases"]
    require(isinstance(entries, list) and 0 < len(entries) <= 1000,
            "INVALID_FIXTURE", "Suite must contain 1..1000 cases")
    seen = set()
    for entry in entries:
        _keys(entry, ("directory", "manifest_sha256"), "suite entry")
        name = entry["directory"]
        require(isinstance(name, str) and ID.fullmatch(name) is not None and name not in seen,
                "INVALID_FIXTURE", "Invalid or duplicated suite directory")
        require((root / name).resolve().parent == root,
                "INVALID_FIXTURE", "Case directory escapes suite")
        _hash(entry["manifest_sha256"], "suite entry")
        seen.add(name)
    results = []
    for entry in entries:
        name = entry["directory"]
        try:
            path = root / name
            # Bounded metadata read happens before hashing the file.
            meta = read_json(path / "manifest.json")
            require(isinstance(meta, dict) and meta.get("case_id") == name,
                    "INVALID_FIXTURE", "Expected a case object with matching case_id")
            digest = hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest()
            require(digest == entry["manifest_sha256"], "CHECKSUM_MISMATCH", "Manifest hash mismatch")
            result = verify_case(path)
            result["manifest_sha256"] = digest
        except ContractError as exc:
            result = {"case_id": name, "passed": False,
                      "error": {"code": exc.code, "message": str(exc)}}
        except OSError as exc:
            result = {"case_id": name, "passed": False,
                      "error": {"code": "IO_ERROR", "message": str(exc)}}
        results.append(result)
    passed = sum(item["passed"] for item in results)
    source = Path(__file__).resolve().parent
    return {
        "format": "inference-reference-report", "version": 1,
        "source": "software_reference", "scope": "phase1a_a1_a3",
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "platform": platform.platform(), "tool": __version__},
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(source.glob("*.py"))},
        "suite_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "passed": passed == len(results), "case_count": len(results),
        "passed_count": passed, "cases": results,
    }
