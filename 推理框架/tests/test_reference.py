import importlib
import unittest

import numpy as np

try:
    contracts = importlib.import_module("inference_ref.contracts")
    reference = importlib.import_module("inference_ref.reference")
    oracle = importlib.import_module("inference_ref.oracle")
    compare = importlib.import_module("inference_ref.compare")
except ModuleNotFoundError:
    contracts = reference = oracle = compare = None


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(reference, "A1/A3 reference implementation is missing")

    def test_hand_calculated_integer_linear_with_bias(self):
        values = {
            "weight": np.array([[1, -2, 3], [-4, 0, 2]], dtype=np.int32),
            "input": np.array([2, -3, 4], dtype=np.int32),
            "bias": np.array([1, -2], dtype=np.int32),
        }
        expected = np.array([21, -2], dtype=np.int32)
        np.testing.assert_array_equal(reference.execute("linear", values), expected)
        np.testing.assert_array_equal(oracle.execute("linear", values), expected)

    def test_fp32_inputs_have_fp64_accumulation(self):
        values = {
            "weight": np.array([[1e8, 1, -1e8]], dtype=np.float32),
            "input": np.ones(3, dtype=np.float32),
        }
        np.testing.assert_array_equal(
            reference.execute("linear", values), np.array([1], dtype=np.float32)
        )
        np.testing.assert_array_equal(
            oracle.execute("linear", values), np.array([1], dtype=np.float32)
        )

    def test_add_and_relu_are_independently_checkable(self):
        for dtype in (np.float32, np.int32):
            a = np.array([[-2, 0, 4], [1, -3, 2]], dtype=dtype)
            b = np.array([[1, 2, -1], [-1, 3, -4]], dtype=dtype)
            for engine in (reference, oracle):
                summed = engine.execute("add", {"a": a, "b": b})
                np.testing.assert_array_equal(
                    summed, np.array([[-1, 2, 3], [0, 0, -2]], dtype=dtype)
                )
                np.testing.assert_array_equal(
                    engine.execute("relu", {"input": summed}),
                    np.array([[0, 2, 3], [0, 0, 0]], dtype=dtype),
                )

    def test_random_non_square_cases_match_independent_numpy(self):
        for seed in range(20):
            rng = np.random.default_rng(seed)
            for dtype in (np.float32, np.int32):
                w = rng.integers(-7, 8, size=(3, 17)).astype(dtype)
                x = rng.integers(-9, 10, size=17).astype(dtype)
                values = {"weight": w, "input": x}
                np.testing.assert_array_equal(
                    reference.execute("linear", values), oracle.execute("linear", values)
                )
        for seed in range(10):
            rng = np.random.default_rng(seed)
            values = {
                "weight": rng.normal(size=(5, 23)).astype(np.float32),
                "input": rng.normal(size=23).astype(np.float32),
            }
            report = compare.compare_arrays(
                reference.execute("linear", values), oracle.execute("linear", values)
            )
            self.assertTrue(report["passed"], report)

    def test_integer_final_overflow_is_rejected(self):
        for op, values in (
            ("add", {"a": np.array([2**31 - 1], np.int32),
                     "b": np.array([1], np.int32)}),
            ("linear", {"weight": np.array([[2**30]], np.int32),
                        "input": np.array([4], np.int32)}),
        ):
            for engine in (reference, oracle):
                with self.subTest(op=op, engine=engine):
                    with self.assertRaises(contracts.ContractError) as error:
                        engine.execute(op, values)
                    self.assertEqual(error.exception.code, "NUMERIC_OVERFLOW")

    def test_integer_wide_intermediate_can_cancel(self):
        values = {
            "weight": np.array([[2**30, 2**30]], np.int32),
            "input": np.array([4, -4], np.int32),
        }
        for engine in (reference, oracle):
            np.testing.assert_array_equal(
                engine.execute("linear", values), np.array([0], np.int32)
            )

    def test_invalid_operations_and_inputs_are_rejected(self):
        cases = [
            ("softmax", {"input": np.ones(2, np.float32)}, "UNSUPPORTED"),
            ("linear", {"weight": np.ones((2, 3), np.float32),
                        "input": np.ones(4, np.float32)}, "INVALID_SHAPE"),
            ("add", {"a": np.ones((2, 1), np.float32),
                     "b": np.ones(2, np.float32)}, "INVALID_SHAPE"),
            ("relu", {"input": np.ones(2, np.float64)}, "UNSUPPORTED"),
            ("relu", {"input": np.array([np.nan], np.float32)}, "NONFINITE"),
            ("relu", {"input": np.array([np.inf], np.float32)}, "NONFINITE"),
            ("relu", {"input": np.empty(0, np.float32)}, "INVALID_SHAPE"),
            ("relu", {"input": np.ones(2, np.float32), "extra": np.ones(2, np.float32)},
             "INVALID_ARGUMENT"),
            ("add", {"a": np.ones(2, np.float32), "b": np.ones(2, np.int32)},
             "INVALID_ARGUMENT"),
        ]
        for op, values, code in cases:
            for engine in (reference, oracle):
                with self.subTest(op=op, code=code):
                    with self.assertRaises(contracts.ContractError) as error:
                        engine.execute(op, values)
                    self.assertEqual(error.exception.code, code)

    def test_fp32_output_overflow_is_rejected(self):
        values = {"a": np.array([3e38], np.float32),
                  "b": np.array([3e38], np.float32)}
        for engine in (reference, oracle):
            with self.assertRaises(contracts.ContractError) as error:
                engine.execute("add", values)
            self.assertEqual(error.exception.code, "NUMERIC_OVERFLOW")

    def test_fp32_boundary_is_decided_after_rounding(self):
        maximum = np.finfo(np.float32).max
        for sign in (1, -1):
            values = {"a": np.array([sign * maximum], np.float32),
                      "b": np.array([sign * 2**100], np.float32)}
            for engine in (reference, oracle):
                np.testing.assert_array_equal(
                    engine.execute("add", values),
                    np.array([sign * maximum], np.float32))
            overflow = {"a": values["a"],
                        "b": np.array([sign * 2**104], np.float32)}
            for engine in (reference, oracle):
                with self.assertRaises(contracts.ContractError) as error:
                    engine.execute("add", overflow)
                self.assertEqual(error.exception.code, "NUMERIC_OVERFLOW")

    def test_tensor_spec_checks_storage_and_bounds(self):
        spec = contracts.TensorSpec("float32", (2, 3), (2, 5))
        self.assertEqual(spec.byte_length, 40)
        for shape, storage in [((0,), (1,)), ((2, 3), (2, 2)),
                               ((True,), (1,)), ((2,), (2, 1)),
                               ((2**63,), (2**63,))]:
            with self.subTest(shape=shape, storage=storage):
                with self.assertRaises(contracts.ContractError):
                    contracts.TensorSpec("float32", shape, storage)
        with self.assertRaises(contracts.ContractError):
            contracts.TensorSpec("int4", (2,), (2,))


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(compare, "A3 comparator is missing")

    def test_scalar_mismatch_uses_empty_coordinate_and_match_uses_null(self):
        import json
        for dtype in (np.int32,np.float32):
            for actual,passed,coordinate in ((2,False,[]),(1,True,None)):
                with self.subTest(dtype=dtype,actual=actual):
                    report = compare.compare_arrays(np.array(1,dtype),np.array(actual,dtype))
                    self.assertEqual(report["passed"],passed)
                    self.assertEqual(report["elements"],1)
                    self.assertEqual(report["mismatch_count"],0 if passed else 1)
                    self.assertEqual(report["first_mismatch"],coordinate)
                    json.dumps(report,allow_nan=False)
        within = compare.compare_arrays(np.array(0,np.float32),np.array(5e-7,np.float32))
        self.assertTrue(within["passed"])
        self.assertIsNone(within["first_mismatch"])

    def test_nonfinite_scalar_mismatch_has_coordinate_and_json_safe_metrics(self):
        import json
        for expected,actual in ((1,np.nan),(1,np.inf),(1,-np.inf),(np.nan,1),(np.inf,np.inf)):
            with self.subTest(expected=expected,actual=actual):
                report = compare.compare_arrays(np.array(expected,np.float32),np.array(actual,np.float32))
                self.assertFalse(report["passed"])
                self.assertEqual(report["first_mismatch"],[])
                self.assertEqual(report["mismatch_count"],1)
                self.assertEqual(report["nonfinite_count"],1)
                json.dumps(report,allow_nan=False)

    def test_integer_is_exact_even_with_large_tolerances(self):
        report = compare.compare_arrays(np.array([100], np.int32),
                                        np.array([101], np.int32), atol=100, rtol=100)
        self.assertFalse(report["passed"])
        self.assertEqual(report["first_mismatch"], [0])

    def test_float_tolerance_and_zero_reference(self):
        report = compare.compare_arrays(np.array([0, 2], np.float32),
                                        np.array([5e-7, 2.000001], np.float32))
        self.assertTrue(report["passed"])
        self.assertEqual(report["relative_error_excluded_count"], 1)
        zero = compare.compare_arrays(np.zeros(2, np.float32), np.zeros(2, np.float32))
        self.assertIsNone(zero["max_relative_error"])

    def test_nonfinite_actual_never_passes_and_is_json_safe(self):
        import json
        report = compare.compare_arrays(np.ones(3, np.float32),
                                        np.array([np.nan, np.inf, -np.inf], np.float32))
        self.assertFalse(report["passed"])
        self.assertEqual(report["nonfinite_count"], 3)
        json.dumps(report, allow_nan=False)

    def test_no_broadcasting_or_dtype_casting(self):
        for actual in (np.ones((1, 2), np.float32), np.ones(2, np.float64)):
            with self.assertRaises(contracts.ContractError):
                compare.compare_arrays(np.ones(2, np.float32), actual)

    def test_invalid_tolerance_is_rejected(self):
        for tol in (-1, float("nan"), float("inf"), True, 10**400):
            with self.assertRaises(contracts.ContractError):
                compare.compare_arrays(np.ones(1, np.float32),
                                        np.ones(1, np.float32), atol=tol)
