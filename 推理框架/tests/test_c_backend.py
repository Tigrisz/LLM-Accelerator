import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

import numpy as np

from inference_ref import reference
from inference_ref.contracts import ContractError
from tests.support import Workspace

try:
    cb = importlib.import_module("inference_ref.c_backend")
except ModuleNotFoundError:
    cb = None

ROOT = Path(__file__).resolve().parents[1]
HAS_CC = any(shutil.which(name) for name in ("cc", "gcc", "clang"))


class CBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAS_CC:
            if os.environ.get("IR_REQUIRE_C") == "1":
                raise RuntimeError("IR_REQUIRE_C=1 but no C compiler is available")
            raise unittest.SkipTest("No native C compiler; run this suite in WSL/Linux with cc")
        if cb is not None:
            cls.workspace = Workspace()
            cls.addClassCleanup(cls.workspace.cleanup)
            cls.artifact = cb.build_backend(Path(cls.workspace.name) / "backend")
            cls.backend = cb.CBackend(cls.artifact)

    def setUp(self):
        self.assertIsNotNone(cb, "A4 C backend implementation is missing")

    def test_frozen_54_cases_and_c_call_chains(self):
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (ROOT / "fixtures/synthetic-v1").rglob("*") if p.is_file()}
        report = cb.verify_c_suite(ROOT / "fixtures/synthetic-v1", self.backend)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["passed_count"], 54)
        self.assertEqual(report["case_count"], 54)
        self.assertEqual(len(report["chains"]), 2)
        self.assertTrue(all(c["completed_steps"] == 4 for c in report["chains"]))
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (ROOT / "fixtures/synthetic-v1").rglob("*") if p.is_file()})
        json.dumps(report, allow_nan=False)

    def test_integer_accumulation_larger_than_int64_can_cancel(self):
        maximum = 2**31 - 1
        inputs = {"weight": np.array([[maximum]*3 + [-maximum]*3], np.int32),
                  "input": np.full(6, maximum, np.int32)}
        np.testing.assert_array_equal(self.backend.execute("linear", inputs), [0])
        np.testing.assert_array_equal(self.backend.execute("linear", inputs),
                                      reference.execute("linear", inputs))

    def test_float_expansion_handles_extreme_cancellation_and_rounding(self):
        maximum = np.finfo(np.float32).max
        tiny = np.nextafter(np.float32(0), np.float32(1))
        inputs = {"weight": np.array([[maximum, tiny, -maximum]], np.float32),
                  "input": np.ones(3, np.float32)}
        np.testing.assert_array_equal(self.backend.execute("linear", inputs),
                                      np.array([tiny], np.float32))
        for sign in (1, -1):
            rounded = self.backend.execute("add", {
                "a": np.array([sign * maximum], np.float32),
                "b": np.array([sign * 2**100], np.float32)})
            np.testing.assert_array_equal(rounded, np.array([sign * maximum], np.float32))

    def test_final_overflow_nonfinite_and_unsupported_are_typed(self):
        cases = [
            ("add", {"a": np.array([2**31-1], np.int32),
                     "b": np.ones(1, np.int32)}, "NUMERIC_OVERFLOW"),
            ("add", {"a": np.array([3e38], np.float32),
                     "b": np.array([3e38], np.float32)}, "NUMERIC_OVERFLOW"),
            ("relu", {"input": np.array([np.nan], np.float32)}, "NONFINITE"),
            ("relu", {"input": np.array([np.inf], np.float32)}, "NONFINITE"),
            ("softmax", {"input": np.ones(2, np.float32)}, "UNSUPPORTED"),
        ]
        for op, inputs, code in cases:
            with self.subTest(code=code, op=op):
                with self.assertRaises(ContractError) as error:
                    self.backend.execute(op, inputs)
                self.assertEqual(error.exception.code, code)

    def test_padded_output_and_failed_output_are_not_overwritten(self):
        a = cb.Tensor(np.array([[-1, 2, 0], [4, -3, 5]], np.float32),
                      storage_shape=(2, 5))
        output = cb.Tensor(np.full((2, 3), -99, np.float32), storage_shape=(2, 5))
        output.storage[:, 3:] = 77
        call = cb.Call("relu", a, output=output)
        self.backend.run(call)
        np.testing.assert_array_equal(output.logical(), [[0, 2, 0], [4, 0, 5]])
        np.testing.assert_array_equal(output.storage[:, 3:], 77)
        a = cb.Tensor(np.array([1, 2**31-1], np.int32))
        b = cb.Tensor(np.array([1, 1], np.int32))
        output = cb.Tensor(np.full(2, -99, np.int32))
        with self.assertRaises(ContractError):
            self.backend.run(cb.Call("add", a, b, output=output))
        np.testing.assert_array_equal(output.logical(), [-99, -99])

    def test_shape_capacity_alias_layout_and_workspace_checks(self):
        for mutation, code in [
            ("short", "INVALID_ARGUMENT"), ("shape", "INVALID_SHAPE"),
            ("rank", "INVALID_SHAPE"), ("layout", "UNSUPPORTED"),
            ("dtype", "UNSUPPORTED"), ("alias", "INVALID_ARGUMENT"),
            ("workspace", "RESOURCE_LIMIT"), ("misalign", "INVALID_ARGUMENT"),
        ]:
            a = cb.Tensor(np.ones(2, np.float32))
            output = cb.Tensor(np.zeros(2, np.float32))
            call = cb.Call("relu", a, output=output)
            if mutation == "short": a.descriptor.byte_length = 1
            if mutation == "shape": output.descriptor.shape[0] = 1
            if mutation == "rank": a.descriptor.rank = 0
            if mutation == "layout": a.descriptor.layout = 99
            if mutation == "dtype": a.descriptor.dtype = 99
            if mutation == "alias": call.descriptor.output = __import__("ctypes").pointer(a.descriptor)
            if mutation == "workspace": call.descriptor.workspace_bytes = 0
            if mutation == "misalign": a.descriptor.data += 1
            with self.subTest(mutation=mutation):
                with self.assertRaises(ContractError) as error:
                    self.backend.run(call)
                self.assertEqual(error.exception.code, code)

    def test_chain_stops_on_failure_and_reports_completed_steps(self):
        a = cb.Tensor(np.array([2**31-1], np.int32))
        first = cb.Tensor(np.array([-10], np.int32))
        second = cb.Tensor(np.array([-20], np.int32))
        last = cb.Tensor(np.array([-30], np.int32))
        calls = [
            cb.Call("relu", a, output=first),
            cb.Call("add", first, cb.Tensor(np.ones(1, np.int32)), output=second),
            cb.Call("relu", second, output=last),
        ]
        status, completed = self.backend.run_chain(calls, raise_on_error=False)
        self.assertEqual(status, "NUMERIC_OVERFLOW")
        self.assertEqual(completed, 1)
        np.testing.assert_array_equal(first.logical(), [2**31-1])
        np.testing.assert_array_equal(second.logical(), [-20])
        np.testing.assert_array_equal(last.logical(), [-30])

    def test_build_metadata_and_no_overwrite(self):
        self.assertTrue(self.artifact.is_file())
        manifest = json.loads((self.artifact.parent / "build.json").read_text())
        self.assertIn("compiler_version", manifest)
        self.assertIn("ir_core.c", manifest["source_sha256"])
        self.assertEqual(hashlib.sha256(self.artifact.read_bytes()).hexdigest(),
                         manifest["binary_sha256"])
        with self.assertRaises(ContractError):
            cb.build_backend(self.artifact.parent)

    def test_completed_counter_cannot_alias_chain_storage(self):
        ct = __import__("ctypes")
        for target in ("input", "output", "workspace", "call", "descriptor"):
            a = cb.Tensor(np.array([7], np.int32))
            output = cb.Tensor(np.array([-99], np.int32))
            call = cb.Call("relu", a, output=output)
            native = (cb.CCall * 1)(call.descriptor)
            if target == "input": address = a.descriptor.data
            elif target == "output":
                native[0].op = 999
                address = output.descriptor.data
            elif target == "workspace": address = call.descriptor.workspace
            elif target == "call": address = ct.addressof(native)
            else: address = ct.addressof(a.descriptor) + cb.CTensor.rank.offset
            counter = ct.cast(address, ct.POINTER(ct.c_uint32))
            before = counter[0]
            with self.subTest(target=target):
                status = self.backend.lib.ir_execute_chain(native, 1, counter)
                self.assertEqual(self.backend._status(status), "INVALID_ARGUMENT")
                self.assertEqual(counter[0], before)
                np.testing.assert_array_equal(a.logical(), [7])
                np.testing.assert_array_equal(output.logical(), [-99])

    def test_chain_numeric_failure_is_reported_and_cli_returns_one(self):
        work = Workspace()
        self.addCleanup(work.cleanup)
        def numeric_failure(calls, *, raise_on_error=True):
            if raise_on_error:
                raise ContractError("NUMERIC_OVERFLOW", "injected C chain numeric failure")
            return "NUMERIC_OVERFLOW", 1
        with mock.patch.object(cb.CBackend, "run_chain", side_effect=numeric_failure):
            result = cb.run_validation(ROOT / "fixtures/synthetic-v1", Path(work.name) / "failure")
            self.assertFalse(result["passed"])
            self.assertEqual(result["passed_count"], 54)
            self.assertTrue(all(c["status"] == "NUMERIC_OVERFLOW" and
                                c["completed_steps"] == 1 and not c["passed"]
                                for c in result["chains"]))
            saved = json.loads((Path(work.name) / "failure/report.json").read_text())
            self.assertFalse(saved["passed"])
            cli = importlib.import_module("inference_ref.__main__")
            with mock.patch.object(cb, "run_validation", return_value=result), mock.patch.object(
                    sys, "argv", ["inference_ref", "verify-c", "--fixtures",
                                  str(ROOT / "fixtures/synthetic-v1"), "--output",
                                  str(Path(work.name) / "cli_failure")]):
                self.assertEqual(cli.main(), 1)

    def test_native_c_tests_and_sanitizers(self):
        result = cb.run_native_tests(Path(self.workspace.name) / "native_tests")
        self.assertTrue(result["passed"], result)
        self.assertTrue(result["sanitizers"])

    def test_verify_c_cli_real_execution_and_no_overwrite(self):
        work = Workspace()
        self.addCleanup(work.cleanup)
        output = Path(work.name) / "cli"
        command = [sys.executable, "-m", "inference_ref", "verify-c", "--fixtures",
                   str(ROOT / "fixtures/synthetic-v1"), "--output", str(output)]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads((output / "report.json").read_text())
        self.assertTrue(result["passed"])
        self.assertEqual(result["source"], "pc_c_backend")
        self.assertEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 2)
