"""End-to-end fixture -> data-only package -> planned arenas -> C execution."""

import hashlib
from pathlib import Path

import numpy as np

from . import oracle, reference
from .c_backend import CBackend, ROOT, _new_directory, build_backend, run_native_tests
from .compare import compare_arrays
from .contracts import ContractError, require
from .fixtures import read_fixture
from .model_package import write_package
from .reporting import write_json_exclusive
from .runtime import create_session, load_model
from .suite import verify_suite


def _record(name, role, dtype, shape, storage=None):
    return {"id": name, "role": role, "dtype": dtype, "layout": "row_major",
            "shape": list(shape), "storage_shape": list(shape if storage is None else storage)}


def package_fixture(path: Path, fixture) -> dict[str, np.ndarray]:
    op = fixture.metadata["operation"]["name"]
    constants = {k: v for k, v in fixture.inputs.items() if op == "linear" and k in {"weight", "bias"}}
    feeds = {k: v for k, v in fixture.inputs.items() if k not in constants}
    records = []
    for t in fixture.metadata["tensors"]:
        name = "y" if t["name"] == "expected" else t["name"]
        role = "output" if name == "y" else "constant" if name in constants else "input"
        records.append(_record(name, role, t["dtype"], t["shape"], t["storage_shape"]))
    write_package(path, model_id="fixture_" + fixture.metadata["case_id"], tensors=records,
                  nodes=[{"id": "operator", "op": op, "inputs": {k:k for k in fixture.inputs}, "output": "y"}],
                  inputs=list(feeds), outputs=["y"], constants=constants)
    return feeds


def chain_definition(dtype):
    records = [_record("x", "input", dtype, (3,)), _record("w", "constant", dtype, (2, 3)),
               _record("bias", "constant", dtype, (2,)), _record("delta", "constant", dtype, (2,)),
               _record("w2", "constant", dtype, (2, 2))]
    records += [_record(name, role, dtype, (2,)) for name, role in
                (("h1", "intermediate"), ("h2", "intermediate"), ("h3", "intermediate"), ("y", "output"))]
    nodes = [{"id": "linear0", "op": "linear", "inputs": {"weight": "w", "input": "x", "bias": "bias"}, "output": "h1"},
             {"id": "relu", "op": "relu", "inputs": {"input": "h1"}, "output": "h2"},
             {"id": "add", "op": "add", "inputs": {"a": "h2", "b": "delta"}, "output": "h3"},
             {"id": "linear1", "op": "linear", "inputs": {"weight": "w2", "input": "h3"}, "output": "y"}]
    constants = {"w": np.array([[1,-2,3],[-4,0,2]], dtype), "bias": np.array([1,-2], dtype),
                 "delta": np.array([1,-1], dtype), "w2": np.array([[1,2],[-1,3]], dtype)}
    return dict(model_id="synthetic_chain", tensors=records, nodes=nodes,
                inputs=["x"], outputs=["y"], constants=constants)


def _evaluate(package, feeds, execute):
    values = dict(feeds)
    for t in package.tensors:
        if t.role == "constant":
            values[t.id] = package.constant_array(t.id)[tuple(slice(0, d) for d in t.spec.shape)].copy()
    for node in package.nodes:
        values[node.output] = execute(node.op, {k:values[v] for k,v in node.inputs})
    return {name: values[name] for name in package.outputs}


def _chains(directory: Path, backend: CBackend) -> list[dict]:
    results = []
    for dtype in ("int32", "float32"):
        path = directory / dtype
        write_package(path, **chain_definition(dtype))
        model = load_model(path)
        feeds = {"x": np.array([2,-3,4], dtype)}
        with create_session(model, backend) as session:
            info = session.memory_info()
            try:
                actual = session.run(feeds)["y"]
                comparisons = {
                    "scalar_vs_runtime": compare_arrays(_evaluate(model.package, feeds, reference.execute)["y"], actual),
                    "numpy_vs_runtime": compare_arrays(_evaluate(model.package, feeds, oracle.execute)["y"], actual),
                    "manual_final": compare_arrays(np.array([20,-25], dtype), actual)}
                repeat = session.run({"x": np.zeros(3, dtype)})["y"]
                comparisons["repeat_manual"] = compare_arrays(np.array([0,-5], dtype), repeat)
                stable = info == session.memory_info()
                results.append({"dtype": dtype, **session.last_result,
                                "passed": all(c["passed"] for c in comparisons.values()) and stable,
                                "comparisons": comparisons, "stable_arena_addresses": stable,
                                "memory_plan": model.plan.to_dict(),
                                "reused_bytes": model.plan.unpooled_bytes-model.plan.total_bytes,
                                "manifest_sha256": model.package.manifest_sha256,
                                "weights_sha256": model.package.weights_sha256})
            except ContractError as exc:
                results.append({"dtype": dtype, **session.last_result, "passed": False,
                                "error": {"code": exc.code, "message": str(exc)}})
    return results


def _hash_tree(root):
    return {str(p.relative_to(root)).replace("\\", "/"):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def run_package_validation(root: Path, output: Path, compiler=None) -> dict:
    root, output = Path(root).resolve(), Path(output).resolve()
    require(not output.is_relative_to(root), "INVALID_ARGUMENT", "Output must be outside fixture tree")
    before = _hash_tree(root)
    baseline = verify_suite(root)
    directory = _new_directory(output)
    backend = CBackend(build_backend(directory / "backend", compiler))
    results = []
    for checked in baseline["cases"]:
        name = checked["case_id"]
        if not checked["passed"]:
            results.append({"case_id": name, "passed": False, "python_validation": checked})
            continue
        try:
            fixture = read_fixture(root / name)
            feeds = package_fixture(directory / "packages" / name, fixture)
            model = load_model(directory / "packages" / name)
            with create_session(model, backend) as session:
                actual = session.run(feeds)["y"]
                status = session.last_result
                backing = session.memory_info()["total_backing_bytes"]
            op, policy = fixture.metadata["operation"]["name"], fixture.metadata["comparison"]
            comparisons = {key: compare_arrays(expected, actual, policy["atol"], policy["rtol"])
                           for key, expected in (
                               ("stored_vs_runtime", fixture.expected),
                               ("scalar_vs_runtime", reference.execute(op, fixture.inputs)),
                               ("numpy_vs_runtime", oracle.execute(op, fixture.inputs)))}
            results.append({"case_id": name, "passed": all(c["passed"] for c in comparisons.values()),
                            "comparisons": comparisons, **status, "memory_plan": model.plan.to_dict(),
                            "actual_backing_bytes": backing, "manifest_sha256": model.package.manifest_sha256,
                            "weights_sha256": model.package.weights_sha256,
                            "fixture_manifest_sha256": checked["manifest_sha256"]})
        except ContractError as exc:
            results.append({"case_id": name, "passed": False, "error": {"code": exc.code, "message": str(exc)}})
    chains = _chains(directory / "chains", backend)
    native = run_native_tests(directory / "native_tests", compiler)
    unchanged = before == _hash_tree(root)
    sources = [ROOT / "inference_ref" / name for name in
               ("model_package.py", "memory.py", "runtime.py", "package_validation.py", "__main__.py")]
    count = sum(c["passed"] for c in results)
    report = {"format": "inference-package-report", "version": 1, "source": "pc_model_package_c",
              "scope": "phase1a_a5", "passed": count == len(results) and all(c["passed"] for c in chains) and
                                                native["passed"] and unchanged and baseline["passed"],
              "case_count": len(results), "passed_count": count, "cases": results, "chains": chains,
              "fixture_files_unchanged": unchanged, "fixture_files_before_sha256": before,
              "suite_sha256": baseline["suite_sha256"], "python_reference_passed": baseline["passed"],
              "python_reference_source_sha256": baseline["source_sha256"], "environment": baseline["environment"],
              "source_sha256": {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              "build": backend.build, "native_tests": native}
    write_json_exclusive(directory / "report.json", report)
    return report
