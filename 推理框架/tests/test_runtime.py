import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

import numpy as np

from inference_ref import c_backend, reference
from inference_ref.contracts import ContractError
from tests.package_support import chain_definition, tensor
from tests.support import Workspace

try:
    runtime = importlib.import_module("inference_ref.runtime")
except ModuleNotFoundError:
    runtime = None

ROOT = Path(__file__).resolve().parents[1]


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not any(shutil.which(n) for n in ("cc", "gcc", "clang")):
            if __import__("os").environ.get("IR_REQUIRE_C") == "1":
                raise RuntimeError("C compiler required for A5")
            raise unittest.SkipTest("C compiler unavailable; use WSL and IR_REQUIRE_C=1")
        cls.work = Workspace()
        cls.addClassCleanup(cls.work.cleanup)
        cls.backend = c_backend.CBackend(c_backend.build_backend(Path(cls.work.name) / "backend"))

    def setUp(self):
        self.assertIsNotNone(runtime, "A5 runtime implementation is missing")
        self.temp = Workspace()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "model"

    def model(self, dtype="int32", padded=False, early=False):
        from inference_ref.model_package import write_package
        definition = chain_definition(dtype, padded)
        if early:
            definition["outputs"] = ["h1", "y"]
            definition["tensors"][5]["role"] = "output"
        write_package(self.path, **definition)
        return runtime.load_model(self.path)

    def test_loaded_padded_and_compact_chains_use_c_and_shared_workspace(self):
        for dtype in ("float32", "int32"):
            for padded in (False, True):
                self.path = Path(self.temp.name) / (dtype + str(padded))
                model = self.model(dtype, padded)
                before = hashlib.sha256(model.package.weights).hexdigest()
                with runtime.create_session(model, self.backend) as session:
                    with mock.patch.object(c_backend, "Tensor", side_effect=AssertionError("per-tensor allocation")), \
                         mock.patch.object(c_backend, "Call", side_effect=AssertionError("per-call allocation")):
                        result = session.run({"x": np.array([2, -3, 4], dtype)})
                    np.testing.assert_array_equal(result["y"], [20, -25])
                    self.assertEqual(session.last_result, {"status": "OK", "completed_steps": 4})
                    info = session.memory_info()
                    self.assertEqual(info["total_backing_bytes"], model.plan.total_bytes)
                    self.assertTrue(all(address % model.plan.alignment == 0 for address in info["arena_addresses"].values()))
                    self.assertEqual(len({int(c.workspace) for c in session._calls}), 1)
                self.assertEqual(hashlib.sha256(model.package.weights).hexdigest(), before)

    def test_repeated_runs_keep_allocations_and_outputs_do_not_alias(self):
        model = self.model()
        with runtime.create_session(model, self.backend) as session:
            info = session.memory_info()
            first = session.run({"x": np.array([2, -3, 4], np.int32)})
            second_input = np.array([0, 0, 0], np.int32)
            second = session.run({"x": second_input})
            np.testing.assert_array_equal(first["y"], [20, -25])
            np.testing.assert_array_equal(second["y"], [0, -5])
            self.assertEqual(info, session.memory_info())
            np.testing.assert_array_equal(second_input, 0)
            second["y"][:] = 999
            np.testing.assert_array_equal(session.run({"x": np.zeros(3, np.int32)})["y"], [0, -5])

    def test_early_output_is_preserved(self):
        model = self.model(early=True)
        with runtime.create_session(model, self.backend) as session:
            result = session.run({"x": np.array([2, -3, 4], np.int32)})
            np.testing.assert_array_equal(result["h1"], [21, -2])
            np.testing.assert_array_equal(result["y"], [20, -25])

    def test_session_isolation_and_close(self):
        model = self.model()
        one = runtime.create_session(model, self.backend)
        two = runtime.create_session(model, self.backend)
        self.addCleanup(one.close)
        self.addCleanup(two.close)
        a, b = one.memory_info()["arena_addresses"], two.memory_info()["arena_addresses"]
        self.assertEqual(a["weights"], b["weights"])
        self.assertNotEqual(a["activations"], b["activations"])
        self.assertNotEqual(a["workspace"], b["workspace"])
        one.close()
        one.close()
        with self.assertRaises(ContractError):
            one.run({"x": np.zeros(3, np.int32)})
        np.testing.assert_array_equal(two.run({"x": np.zeros(3, np.int32)})["y"], [0, -5])

    def test_bad_inputs_numeric_failure_and_retry(self):
        model = self.model("float32", padded=True)
        with runtime.create_session(model, self.backend) as session:
            for feeds in ({}, {"bad": np.zeros(3, np.float32)},
                          {"x": np.zeros(2, np.float32)}, {"x": np.zeros(3, np.float64)},
                          {"x": np.array([np.nan, 0, 0], np.float32)}):
                with self.subTest(feeds=str(feeds)), self.assertRaises(ContractError):
                    session.run(feeds)
            with self.assertRaises(ContractError) as caught:
                session.run({"x": np.full(3, np.finfo(np.float32).max, np.float32)})
            self.assertEqual(caught.exception.code, "NUMERIC_OVERFLOW")
            self.assertEqual(session.last_result["status"], "NUMERIC_OVERFLOW")
            np.testing.assert_array_equal(session.run({"x": np.zeros(3, np.float32)})["y"], [0, -5])

    def test_budget_rejected_before_arena_allocation(self):
        model = self.model()
        with mock.patch.object(runtime, "Arena", side_effect=AssertionError("allocated before budget check")):
            with self.assertRaises(ContractError) as caught:
                runtime.load_model(self.path, memory_budget=model.plan.total_bytes-1)
            self.assertEqual(caught.exception.code, "RESOURCE_LIMIT")
            with self.assertRaises(ContractError):
                runtime.create_session(model, self.backend, memory_budget=model.plan.total_bytes-1)
        inspected = runtime.inspect_model(self.path)
        self.assertEqual(inspected["memory_plan"]["total_bytes"], model.plan.total_bytes)

    def test_model_with_no_constants_and_multiple_inputs(self):
        from inference_ref.model_package import write_package
        write_package(self.path, model_id="add", tensors=[tensor("a", "input", "int32", (2,)),
                      tensor("b", "input", "int32", (2,)), tensor("y", "output", "int32", (2,))],
                      nodes=[{"id": "sum", "op": "add", "inputs": {"a": "a", "b": "b"}, "output": "y"}],
                      inputs=["a", "b"], outputs=["y"], constants={})
        model = runtime.load_model(self.path)
        self.assertEqual(model.plan.weight_bytes, 0)
        with runtime.create_session(model, self.backend) as session:
            result = session.run({"a": np.array([-2, 3], np.int32), "b": np.array([4, -5], np.int32)})
            np.testing.assert_array_equal(result["y"], [2, -2])

    def test_package_validation_cli_and_frozen_inputs_unchanged(self):
        original = {str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (ROOT / "fixtures/synthetic-v1").rglob("*") if p.is_file()}
        output = Path(self.temp.name) / "validation"
        command = [sys.executable, "-m", "inference_ref", "verify-packages", "--fixtures",
                   str(ROOT / "fixtures/synthetic-v1"), "--output", str(output)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads((output / "report.json").read_text())
        self.assertEqual(report["passed_count"], 54)
        self.assertTrue(report["passed"])
        self.assertTrue(all(c["passed"] and c["reused_bytes"] > 0 for c in report["chains"]))
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
        command = [sys.executable, "-m", "inference_ref", "inspect-model", "--package",
                   str(output / "chains/int32")]
        inspected = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["node_count"], 4)
        self.assertEqual(original, {str(p):hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in (ROOT / "fixtures/synthetic-v1").rglob("*") if p.is_file()})

    def test_generated_fanout_graphs_match_scalar_and_numpy(self):
        from inference_ref import oracle
        from inference_ref.model_package import write_package
        rng = np.random.default_rng(20261024)
        for index in range(24):
            dtype = "int32" if index % 2 else "float32"
            shape, storage = (2, 3), (2, 5)
            records = [tensor("x", "input", dtype, shape), tensor("delta", "constant", dtype, shape)]
            delta = rng.integers(-3, 4, shape).astype(dtype)
            feeds = rng.integers(-5, 6, shape).astype(dtype)
            scalar, numpy_values = {"x": feeds, "delta": delta}, {"x": feeds, "delta": delta}
            nodes = []
            for i in range(8):
                name, previous = f"h{i}", "x" if i == 0 else f"h{i-1}"
                role = "output" if i in (2, 7) else "intermediate"
                records.append(tensor(name, role, dtype, shape, storage if rng.integers(2) else shape))
                op = "add" if i % 2 == 0 else "relu"
                bound = {"a": previous, "b": "delta" if i == 0 else f"h{int(rng.integers(i))}"} if op == "add" else {"input": previous}
                nodes.append({"id": f"n{i}", "op": op, "inputs": bound, "output": name})
                scalar[name] = reference.execute(op, {k:scalar[v] for k,v in bound.items()})
                numpy_values[name] = oracle.execute(op, {k:numpy_values[v] for k,v in bound.items()})
            path = Path(self.temp.name) / f"fanout{index}"
            write_package(path, model_id="fanout", tensors=records, nodes=nodes,
                          inputs=["x"], outputs=["h2", "h7"], constants={"delta": delta})
            model = runtime.load_model(path)
            with runtime.create_session(model, self.backend) as session:
                for _ in range(2):
                    actual = session.run({"x": feeds})
                    for name in ("h2", "h7"):
                        np.testing.assert_array_equal(actual[name], scalar[name])
                        np.testing.assert_array_equal(actual[name], numpy_values[name])
