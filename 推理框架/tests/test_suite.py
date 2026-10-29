import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

from inference_ref.contracts import ContractError
from inference_ref.fixtures import read_fixture, write_fixture
from tests.support import Workspace

try:
    suite = importlib.import_module("inference_ref.suite")
except ModuleNotFoundError:
    suite = None

ROOT = Path(__file__).resolve().parents[1]


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(suite, "A3 suite generation/verification is missing")
        self.temp = Workspace()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_generation_is_deterministic_and_all_cases_verify(self):
        first, second = self.root / "first", self.root / "second"
        suite.generate_suite(first)
        suite.generate_suite(second)
        a = {p.relative_to(first).as_posix(): p.read_bytes()
             for p in first.rglob("*") if p.is_file()}
        b = {p.relative_to(second).as_posix(): p.read_bytes()
             for p in second.rglob("*") if p.is_file()}
        self.assertEqual(a, b)
        result = suite.verify_suite(first)
        self.assertTrue(result["passed"], result)
        self.assertGreaterEqual(result["case_count"], 50)
        self.assertEqual(result["passed_count"], result["case_count"])
        json.dumps(result, allow_nan=False)

    def test_wrong_expected_is_detected_even_when_all_checksums_match(self):
        output = self.root / "cases"
        suite.generate_suite(output)
        path = output / "int_hand_bias"
        meta = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        data = bytearray((path / "data.bin").read_bytes())
        record = next(t for t in meta["tensors"] if t["name"] == "expected")
        data[record["offset"]] ^= 1
        (path / "data.bin").write_bytes(data)
        meta["payload"]["sha256"] = hashlib.sha256(data).hexdigest()
        record["sha256"] = hashlib.sha256(
            data[record["offset"]:record["offset"] + record["byte_length"]]
        ).hexdigest()
        (path / "manifest.json").write_text(json.dumps(meta), encoding="utf-8")
        index = json.loads((output / "suite.json").read_text(encoding="utf-8"))
        entry = next(x for x in index["cases"] if x["directory"] == "int_hand_bias")
        entry["manifest_sha256"] = hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest()
        (output / "suite.json").write_text(json.dumps(index), encoding="utf-8")
        report = suite.verify_suite(output)
        self.assertFalse(report["passed"])
        failed = next(x for x in report["cases"] if x["case_id"] == "int_hand_bias")
        self.assertFalse(failed["comparisons"]["stored_vs_scalar"]["passed"])
        self.assertTrue(failed["comparisons"]["scalar_vs_numpy"]["passed"])

    def test_missing_or_corrupted_case_is_reported_without_aborting_other_cases(self):
        output = self.root / "cases"
        suite.generate_suite(output)
        (output / "int_hand_bias" / "data.bin").write_bytes(b"bad")
        report = suite.verify_suite(output)
        self.assertFalse(report["passed"])
        self.assertEqual(report["passed_count"], report["case_count"] - 1)
        self.assertIn("error", next(x for x in report["cases"] if x["case_id"] == "int_hand_bias"))

    def test_index_path_traversal_and_duplicate_cases_are_rejected(self):
        output = self.root / "cases"
        suite.generate_suite(output)
        original = json.loads((output / "suite.json").read_text(encoding="utf-8"))
        for name in ("../outside", "C:/outside", ""):
            index = json.loads(json.dumps(original))
            index["cases"][0]["directory"] = name
            (output / "suite.json").write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaises(ContractError):
                suite.verify_suite(output)
        original["cases"].append(original["cases"][0])
        (output / "suite.json").write_text(json.dumps(original), encoding="utf-8")
        with self.assertRaises(ContractError):
            suite.verify_suite(output)

    def test_float_fixture_roundtrip_and_nonfinite_rejection(self):
        output = self.root / "float"
        write_fixture(output, "float_case", "relu",
                      {"input": np.array([-1, 0, 2.5], np.float32)},
                      np.array([0, 0, 2.5], np.float32),
                      provenance={"kind": "manual", "source": "literal values", "seed": None})
        self.assertEqual(read_fixture(output).metadata["comparison"]["mode"], "abs_plus_rel")

    def test_nonobject_case_manifest_is_reported_as_invalid_fixture(self):
        output = self.root / "cases"
        suite.generate_suite(output)
        path = output / "int_hand_bias" / "manifest.json"
        index = json.loads((output / "suite.json").read_text(encoding="utf-8"))
        entry = next(x for x in index["cases"] if x["directory"] == "int_hand_bias")
        for malformed in ([], None, 3, "text"):
            path.write_text(json.dumps(malformed), encoding="utf-8")
            entry["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            (output / "suite.json").write_text(json.dumps(index), encoding="utf-8")
            report = suite.verify_suite(output)
            self.assertFalse(report["passed"])
            case = next(x for x in report["cases"] if x["case_id"] == "int_hand_bias")
            self.assertEqual(case["error"]["code"], "INVALID_FIXTURE")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = Workspace()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "inference_ref", *map(str, arguments)],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_cli_generate_verify_and_failure_exit_codes(self):
        cases, report = self.root / "cases", self.root / "report.json"
        generated = self.run_cli("generate", "--output", cases)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        verified = self.run_cli("verify", "--fixtures", cases, "--report", report)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertTrue(json.loads(report.read_text())["passed"])
        no_overwrite = self.run_cli("verify", "--fixtures", cases, "--report", report)
        self.assertEqual(no_overwrite.returncode, 2)
        self.assertEqual(self.run_cli("generate", "--output", cases).returncode, 2)
        (cases / "int_hand_bias" / "data.bin").write_bytes(b"broken")
        failed = self.run_cli("verify", "--fixtures", cases, "--report", self.root / "failed.json")
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertFalse(json.loads((self.root / "failed.json").read_text())["passed"])

    def test_report_cannot_be_written_inside_input_suite(self):
        cases = self.root / "cases"
        generated = self.run_cli("generate", "--output", cases)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        result = self.run_cli("verify", "--fixtures", cases,
                              "--report", cases / "new_report.json")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((cases / "new_report.json").exists())
