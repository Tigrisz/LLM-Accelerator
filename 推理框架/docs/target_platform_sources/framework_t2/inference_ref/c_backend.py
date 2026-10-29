"""PC-only C11 build/binding and alignment checks. No numerical Python fallback."""

import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import numpy as np

from . import oracle, reference
from .compare import compare_arrays
from .contracts import ContractError, TensorSpec, require
from .fixtures import read_fixture
from .reporting import write_json_exclusive
from .suite import verify_suite

ROOT = Path(__file__).resolve().parents[1]
OPS = {"linear": 1, "add": 2, "relu": 3}
DTYPES = {"float32": 1, "int32": 2}
FLAGS = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-fno-fast-math", "-ffp-contract=off", "-fexcess-precision=standard"]


class CTensor(ct.Structure):
    _fields_ = [("data", ct.c_void_p), ("byte_length", ct.c_uint64),
                ("dtype", ct.c_uint32), ("layout", ct.c_uint32), ("rank", ct.c_uint32),
                ("shape", ct.c_uint64 * 4), ("storage_shape", ct.c_uint64 * 4)]


class CCall(ct.Structure):
    _fields_ = [("op", ct.c_uint32), ("a", ct.POINTER(CTensor)),
                ("b", ct.POINTER(CTensor)), ("bias", ct.POINTER(CTensor)),
                ("output", ct.POINTER(CTensor)), ("workspace", ct.c_void_p),
                ("workspace_bytes", ct.c_uint64)]


class CProfile(ct.Structure):
    _fields_ = [("executed", ct.c_uint32), ("status", ct.c_uint32),
                ("start_ticks", ct.c_uint64), ("end_ticks", ct.c_uint64),
                ("timing_valid", ct.c_uint32), ("reserved", ct.c_uint32)]


class Tensor:
    def __init__(self, values: np.ndarray, storage_shape: tuple | None = None):
        require(isinstance(values, np.ndarray), "INVALID_ARGUMENT", "Tensor needs ndarray")
        self.spec = TensorSpec(values.dtype.name, tuple(values.shape),
                               tuple(values.shape) if storage_shape is None else storage_shape)
        self.storage = np.zeros(self.spec.storage_shape, dtype=self.spec.dtype)
        self.slices = tuple(slice(0, d) for d in self.spec.shape)
        self.storage[self.slices] = values
        self.descriptor = CTensor(
            self.storage.ctypes.data, self.storage.nbytes, DTYPES[self.spec.dtype], 1,
            len(self.spec.shape), (ct.c_uint64 * 4)(*self.spec.shape),
            (ct.c_uint64 * 4)(*self.spec.storage_shape))

    def logical(self) -> np.ndarray:
        return self.storage[self.slices].copy()


class Call:
    def __init__(self, op: str, a: Tensor, b: Tensor | None = None,
                 bias: Tensor | None = None, *, output: Tensor):
        require(isinstance(op, str) and op in OPS, "UNSUPPORTED", "Unknown C operator")
        self.tensors = (a, b, bias, output)
        require(isinstance(a, Tensor) and isinstance(output, Tensor) and
                all(t is None or isinstance(t, Tensor) for t in (b, bias)),
                "INVALID_ARGUMENT", "Call requires Tensor bindings")
        self.workspace = np.empty(output.logical().size, dtype=np.uint32)
        self.descriptor = CCall(
            OPS[op], ct.pointer(a.descriptor),
            ct.pointer(b.descriptor) if b is not None else None,
            ct.pointer(bias.descriptor) if bias is not None else None,
            ct.pointer(output.descriptor), self.workspace.ctypes.data, self.workspace.nbytes)


def _compiler(compiler: str | None) -> str:
    candidate = compiler or next((shutil.which(c) for c in ("cc", "gcc", "clang")
                                  if shutil.which(c)), None)
    require(candidate is not None, "TOOL_UNAVAILABLE",
            "No C compiler: use WSL/Linux with cc, or explicitly select a compiler")
    return str(candidate)


def _new_directory(path: Path) -> Path:
    path = Path(path).resolve()
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ContractError("ALREADY_EXISTS", f"Refuse to overwrite {path}") from exc
    except OSError as exc:
        raise ContractError("IO_ERROR", str(exc)) from exc
    return path


def _run(command: list[str], *, env=None, timeout=120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContractError("TOOL_ERROR", str(exc)) from exc


def _source_hashes(include_tests=False) -> dict:
    files = [ROOT / "c/include/ir_core.h", ROOT / "c/src/ir_core.c"]
    if include_tests:
        files.append(ROOT / "c/tests/test_core.c")
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def build_backend(output: Path, compiler: str | None = None) -> Path:
    cc = _compiler(compiler)
    version = _run([cc, "--version"])
    require(version.returncode == 0, "TOOL_ERROR", version.stderr)
    directory = _new_directory(output)
    suffix = ".dll" if os.name == "nt" else ".dylib" if sys.platform == "darwin" else ".so"
    library = directory / ("libir_core" + suffix)
    link = ["-dynamiclib"] if sys.platform == "darwin" else ["-shared"]
    if os.name != "nt":
        link.append("-fPIC")
    command = [cc, *FLAGS, "-O2", *link, "-I", str(ROOT / "c/include"),
               str(ROOT / "c/src/ir_core.c"), "-lm", "-o", str(library)]
    run = _run(command)
    (directory / "build.log").write_text(run.stdout + run.stderr, encoding="utf-8")
    require(run.returncode == 0 and library.is_file(), "BUILD_FAILED",
            f"C compile failed; see {directory / 'build.log'}")
    write_json_exclusive(directory / "build.json", {
        "compiler_version": version.stdout.strip(), "command": command,
        "source_sha256": _source_hashes(),
        "binary_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "platform": platform.platform(), "abi_version": 1,
    })
    return library


class CBackend:
    def __init__(self, artifact: Path):
        self.artifact = Path(artifact).resolve()
        try:
            self.build = json.loads((self.artifact.parent / "build.json").read_text(encoding="utf-8"))
            require(hashlib.sha256(self.artifact.read_bytes()).hexdigest() ==
                    self.build["binary_sha256"], "CHECKSUM_MISMATCH", "C binary hash mismatch")
            self.lib = ct.CDLL(str(self.artifact))
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise ContractError("IO_ERROR", str(exc)) from exc
        self.lib.ir_abi_version.restype = ct.c_uint32
        self.lib.ir_tensor_struct_size.restype = ct.c_size_t
        self.lib.ir_call_struct_size.restype = ct.c_size_t
        require(self.lib.ir_abi_version() == 1 and
                self.lib.ir_tensor_struct_size() == ct.sizeof(CTensor) and
                self.lib.ir_call_struct_size() == ct.sizeof(CCall),
                "UNSUPPORTED", "C ABI version or structure size mismatch")
        self.lib.ir_status_name.argtypes = [ct.c_int]
        self.lib.ir_status_name.restype = ct.c_char_p
        for name in ("ir_query", "ir_execute"):
            fn = getattr(self.lib, name)
            fn.argtypes = [ct.POINTER(CCall)]
            fn.restype = ct.c_int
        self.lib.ir_execute_chain.argtypes = [ct.POINTER(CCall), ct.c_uint32,
                                             ct.POINTER(ct.c_uint32)]
        self.lib.ir_execute_chain.restype = ct.c_int
        self.has_profiling = all(hasattr(self.lib, name) for name in
            ("ir_execute_chain_profiled", "ir_profile_struct_size", "ir_clock_ticks_per_second"))
        if self.has_profiling:
            self.lib.ir_profile_struct_size.restype = ct.c_size_t
            self.lib.ir_clock_ticks_per_second.restype = ct.c_uint64
            self.has_profiling = self.lib.ir_profile_struct_size() == ct.sizeof(CProfile)
            if self.has_profiling:
                self.lib.ir_execute_chain_profiled.argtypes = [ct.POINTER(CCall), ct.c_uint32,
                    ct.POINTER(ct.c_uint32), ct.POINTER(CProfile), ct.c_uint32]
                self.lib.ir_execute_chain_profiled.restype = ct.c_int

    def _status(self, value: int) -> str:
        return self.lib.ir_status_name(value).decode("ascii")

    def run(self, call: Call) -> None:
        status = self._status(self.lib.ir_execute(ct.byref(call.descriptor)))
        if status != "OK":
            raise ContractError(status, f"C ir_execute returned {status}")

    def run_chain(self, calls: list[Call], *, raise_on_error=True) -> tuple[str, int]:
        require(isinstance(calls, list) and 0 < len(calls) <= 1024,
                "INVALID_ARGUMENT", "C chain requires 1..1024 calls")
        native = (CCall * len(calls))(*(call.descriptor for call in calls))
        completed = ct.c_uint32(0)
        status = self._status(self.lib.ir_execute_chain(native, len(calls), ct.byref(completed)))
        if status != "OK" and raise_on_error:
            raise ContractError(status, f"C chain failed after {completed.value} steps: {status}")
        return status, completed.value

    def execute(self, op: str, inputs: dict[str, np.ndarray], *,
                storage_shapes: dict | None = None) -> np.ndarray:
        allowed = {"linear": ({"weight", "input"}, {"weight", "input", "bias"}),
                   "add": ({"a", "b"},), "relu": ({"input"},)}
        require(isinstance(op, str) and op in allowed, "UNSUPPORTED", "Unknown C operator")
        require(isinstance(inputs, dict) and set(inputs) in allowed[op],
                "INVALID_ARGUMENT", "Wrong C operator input bindings")
        storage_shapes = {} if storage_shapes is None else storage_shapes
        bound = {name: Tensor(value, storage_shapes.get(name)) for name, value in inputs.items()}
        a = bound["weight"] if op == "linear" else bound["a"] if op == "add" else bound["input"]
        b = bound["input"] if op == "linear" else bound.get("b")
        shape = (a.spec.shape[0],) if op == "linear" else a.spec.shape
        output = Tensor(np.zeros(shape, dtype=a.spec.dtype), storage_shapes.get("output"))
        call = Call(op, a, b, bound.get("bias"), output=output)
        self.run(call)
        return output.logical()


def verify_chains(backend: CBackend) -> list[dict]:
    results = []
    for dtype in (np.int32, np.float32):
        w = np.array([[1, -2, 3], [-4, 0, 2]], dtype)
        x = np.array([2, -3, 4], dtype)
        bias = np.array([1, -2], dtype)
        delta = np.array([1, -1], dtype)
        w2 = np.array([[1, 2], [-1, 3]], dtype)
        outputs = [Tensor(np.zeros(2, dtype)) for _ in range(4)]
        calls = [
            Call("linear", Tensor(w), Tensor(x), Tensor(bias), output=outputs[0]),
            Call("relu", outputs[0], output=outputs[1]),
            Call("add", outputs[1], Tensor(delta), output=outputs[2]),
            Call("linear", Tensor(w2), outputs[2], output=outputs[3]),
        ]
        status, completed = backend.run_chain(calls, raise_on_error=False)
        expected = []
        expected.append(reference.execute("linear", {"weight": w, "input": x, "bias": bias}))
        expected.append(reference.execute("relu", {"input": expected[0]}))
        expected.append(reference.execute("add", {"a": expected[1], "b": delta}))
        expected.append(reference.execute("linear", {"weight": w2, "input": expected[2]}))
        comparisons = [compare_arrays(ref, actual.logical()) for ref, actual in zip(expected, outputs)]
        manual = compare_arrays(np.array([20, -25], dtype), outputs[-1].logical())
        results.append({"dtype": np.dtype(dtype).name, "status": status,
                        "completed_steps": completed, "comparisons": comparisons,
                        "manual_final": manual,
                        "passed": status == "OK" and completed == 4 and manual["passed"] and
                                  all(x["passed"] for x in comparisons)})
    return results


def verify_c_suite(root: Path, backend: CBackend) -> dict:
    root = Path(root).resolve()
    baseline = verify_suite(root)
    results = []
    for checked in baseline["cases"]:
        name = checked["case_id"]
        if not checked["passed"]:
            results.append({"case_id": name, "passed": False, "python_validation": checked})
            continue
        try:
            fixture = read_fixture(root / name)
            op = fixture.metadata["operation"]["name"]
            shapes = {r["name"] if r["name"] != "expected" else "output":
                      tuple(r["storage_shape"]) for r in fixture.metadata["tensors"]}
            actual = backend.execute(op, fixture.inputs, storage_shapes=shapes)
            policy = fixture.metadata["comparison"]
            comparisons = {
                "stored_vs_c": compare_arrays(fixture.expected, actual, policy["atol"], policy["rtol"]),
                "scalar_vs_c": compare_arrays(reference.execute(op, fixture.inputs), actual,
                                               policy["atol"], policy["rtol"]),
                "numpy_vs_c": compare_arrays(oracle.execute(op, fixture.inputs), actual,
                                              policy["atol"], policy["rtol"]),
            }
            results.append({"case_id": name, "dtype": actual.dtype.name, "operation": op,
                            "passed": all(x["passed"] for x in comparisons.values()),
                            "comparisons": comparisons,
                            "manifest_sha256": checked["manifest_sha256"]})
        except ContractError as exc:
            results.append({"case_id": name, "passed": False,
                            "error": {"code": exc.code, "message": str(exc)}})
    chains = verify_chains(backend)
    passed = sum(x["passed"] for x in results)
    return {
        "format": "inference-c-report", "version": 1, "source": "pc_c_backend",
        "scope": "phase1a_a4", "passed": passed == len(results) and all(c["passed"] for c in chains),
        "case_count": len(results), "passed_count": passed, "cases": results, "chains": chains,
        "build": backend.build, "suite_sha256": baseline["suite_sha256"],
        "python_reference_passed": baseline["passed"],
        "python_source_sha256": baseline["source_sha256"],
        "environment": baseline["environment"],
    }


def run_native_tests(output: Path, compiler: str | None = None) -> dict:
    cc = _compiler(compiler)
    directory = _new_directory(output)
    executable = directory / ("core_tests.exe" if os.name == "nt" else "core_tests")
    command = [cc, *FLAGS, "-O1", "-g", "-fsanitize=address,undefined",
               "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
               "-I", str(ROOT / "c/include"), str(ROOT / "c/src/ir_core.c"),
               str(ROOT / "c/tests/test_core.c"), "-lm", "-o", str(executable)]
    build = _run(command)
    (directory / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
    require(build.returncode == 0, "BUILD_FAILED", f"Sanitizer build failed: {directory}")
    env = {**os.environ, "ASAN_OPTIONS": "detect_leaks=1:halt_on_error=1",
           "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"}
    run = _run([str(executable)], env=env)
    (directory / "run.log").write_text(run.stdout + run.stderr, encoding="utf-8")
    result = {"passed": run.returncode == 0 and "C_CORE_TESTS_PASS" in run.stdout,
              "sanitizers": ["address", "undefined"], "returncode": run.returncode,
              "command": command, "source_sha256": _source_hashes(True),
              "binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "stdout": run.stdout, "stderr": run.stderr}
    write_json_exclusive(directory / "result.json", result)
    return result


def run_validation(root: Path, output: Path, compiler: str | None = None) -> dict:
    root, output = Path(root).resolve(), Path(output).resolve()
    require(not output.is_relative_to(root), "INVALID_ARGUMENT",
            "C validation output must be outside the fixture tree")
    directory = _new_directory(output)
    backend = CBackend(build_backend(directory / "backend", compiler))
    result = verify_c_suite(root, backend)
    result["native_tests"] = run_native_tests(directory / "native_tests", compiler)
    result["passed"] = result["passed"] and result["native_tests"]["passed"]
    write_json_exclusive(directory / "report.json", result)
    return result
