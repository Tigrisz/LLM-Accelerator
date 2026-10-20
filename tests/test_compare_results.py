import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from scripts.compare_results import compare, golden_values, int32, load_capture

ROOT = Path(__file__).resolve().parents[1]


class CompareResultsTests(unittest.TestCase):
    def setUp(self):
        self.expected = [[-2147483648, 2147483647], [-1, 0]]
        self.capture = dict(format_version=1, source="synthetic", run_id="unit",
                            completed=True, results=[
                                dict(row_id=r, group_id=g, partial_sum=v)
                                for r, row in enumerate(self.expected) for g, v in enumerate(row)])

    def test_signed_hex_and_multigroup(self):
        for value, expected in [("0x80000000", -2147483648), ("0xffffffff", -1), ("0x7fffffff", 2147483647)]:
            self.assertEqual(int32(value), expected)
        self.capture["results"][2]["partial_sum"] = "0xffffffff"
        self.assertEqual(compare(self.expected, self.capture)["status"], "pass")

    def test_value_first_error(self):
        self.capture["results"][2]["partial_sum"] = 7
        error = compare(self.expected, self.capture)["first_error"]
        self.assertEqual((error["kind"], error["row_id"], error["group_id"], error["delta"]), ("value", 1, 0, 8))

    def test_missing_duplicate_and_unexpected(self):
        self.capture["results"].pop()
        self.capture["results"].append(copy.copy(self.capture["results"][0]))
        self.capture["results"].append(dict(row_id=10, group_id=0, partial_sum=0))
        errors = compare(self.expected, self.capture)["error_counts"]
        for key in ("missing", "duplicate", "unexpected_tag", "order"):
            self.assertIn(key, errors)

    def test_order(self):
        self.capture["results"].reverse()
        result = compare(self.expected, self.capture)
        self.assertEqual(result["error_counts"], {"order": 4})

    def test_incomplete_and_empty(self):
        self.capture["completed"] = False
        self.capture["results"] = []
        self.assertEqual(compare(self.expected, self.capture)["error_counts"],
                         {"incomplete_capture": 1, "missing": 4})

    def test_malformed_numeric_values(self):
        for value in (True, 1.5, 2147483648, -2147483649, "12", "0xff", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                int32(value)
        self.capture["results"][0]["row_id"] = True
        with self.assertRaises(ValueError):
            compare(self.expected, self.capture)

    def test_headers(self):
        for key, value in (("format_version", True), ("source", "unknown"), ("run_id", ""), ("completed", 1)):
            capture = copy.deepcopy(self.capture)
            capture[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                compare(self.expected, capture)

    def test_golden_shape_and_dtype(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"golden.npy"
            np.save(path, np.array(self.expected, dtype=np.int32))
            self.assertEqual(golden_values(path), self.expected)
            with self.assertRaises(ValueError):
                golden_values(path, rows=1)
            np.save(path, np.array(self.expected, dtype=np.int64))
            with self.assertRaises(ValueError):
                golden_values(path)

    def test_cli_reports_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            golden, capture, report = d/"expected.mem", d/"capture.json", d/"report.json"
            golden.write_text("80000000 7fffffff ffffffff 00000000")
            command = [sys.executable, str(ROOT/"scripts/compare_results.py"), "--golden", str(golden),
                       "--rows", "2", "--groups", "2", "--capture", str(capture), "--report", str(report)]
            for state, code in (("pass", 0), ("mismatch", 1), ("input_error", 2)):
                payload = copy.deepcopy(self.capture)
                if state == "mismatch":
                    payload["results"].pop()
                capture.write_text(json.dumps(payload) if state != "input_error" else '{"broken":')
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(json.loads(report.read_text())["status"], state)
            capture.write_text(json.dumps(self.capture))
            bitstream = d/"test.sbit"
            bitstream.write_bytes(b"synthetic test bytes")
            result = subprocess.run(command+["--bitstream", str(bitstream)], capture_output=True)
            self.assertEqual(result.returncode, 2)
            # Report/input collision must leave input untouched.
            original = capture.read_bytes()
            result = subprocess.run(command[:-1]+[str(capture)], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(capture.read_bytes(), original)

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"capture.json"
            path.write_text('{"completed":false,"completed":true}')
            with self.assertRaises(ValueError):
                load_capture(path)


if __name__ == "__main__":
    unittest.main()
