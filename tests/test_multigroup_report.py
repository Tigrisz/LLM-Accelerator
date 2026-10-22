"""A failed repeat must never advertise captures from an earlier passing run."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_multigroup_uart as checker

ROOT = Path(__file__).resolve().parents[1]


class MultigroupReportTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "tests/fixtures/a_multigroup",
                        self.root / "tests/fixtures/a_multigroup")
        self.reports = self.root / "build/reports/a_multigroup"
        previous = self.reports / "runs/previous/lanes16_n3_k256/complete"
        previous.mkdir(parents=True)
        self.old_capture = previous / "sim_run1.json"
        self.old_capture.write_text('{"previous": true}\n')
        self.old_summary = {"status": "pass", "attempt_id": "previous",
                            "cases": [{"comparison": "pass"}]}
        checker.save_json(self.reports / "summary.json", self.old_summary)

    def assert_failure_is_current_and_history_is_preserved(self, action):
        with patch.object(checker, "ROOT", self.root), patch.object(
                checker.subprocess, "run", side_effect=action):
            with self.assertRaises((SystemExit, RuntimeError, ValueError,
                                    subprocess.TimeoutExpired)):
                checker.main()
        summary = json.loads((self.reports / "summary.json").read_text())
        self.assertEqual(summary["status"], "failed")
        self.assertNotEqual(summary["attempt_id"], "previous")
        self.assertFalse(summary["board_verified"])
        self.assertTrue(summary["error"])
        self.assertEqual(self.old_capture.read_text(), '{"previous": true}\n')
        attempt = self.reports / "runs" / summary["attempt_id"]
        self.assertTrue((attempt / "lanes16_n3_k256/complete/simulation.log").is_file())
        self.assertFalse(list(attempt.rglob("sim_run*.json")))
        self.assertEqual(json.loads((attempt / "summary.json").read_text()), summary)

    def test_failed_make_replaces_previous_success_status(self):
        def failure(command, **kwargs):
            active = json.loads((self.reports / "summary.json").read_text())
            self.assertEqual(active["status"], "running")
            self.assertEqual(active["cases"], [])
            return subprocess.CompletedProcess(command, 2)
        self.assert_failure_is_current_and_history_is_preserved(failure)

    def test_timeout_replaces_previous_success_status(self):
        def timeout(command, **kwargs):
            raise subprocess.TimeoutExpired(command, 240)
        self.assert_failure_is_current_and_history_is_preserved(timeout)

    def test_bad_new_frame_does_not_reuse_previous_json(self):
        def corrupt_frame(command, **kwargs):
            output_arg = next(x for x in command if x.startswith("A_CAPTURE_REPORT_DIR="))
            output = self.root / output_arg.split("=", 1)[1]
            (output / "sim_run1.bin").write_bytes(b"bad uart frame")
            return subprocess.CompletedProcess(command, 0)
        self.assert_failure_is_current_and_history_is_preserved(corrupt_frame)

    def test_direct_make_runs_separate_depths(self):
        def directory(depth):
            result = subprocess.run(
                ["make", "--no-print-directory", "-f", str(ROOT / "Makefile"),
                 "--eval=print-report-dir:;@echo $(A_CAPTURE_REPORT_DIR)",
                 "print-report-dir", f"A_CAPTURE_DEPTH={depth}"],
                cwd=ROOT, text=True, capture_output=True, check=True)
            return result.stdout.strip()
        self.assertNotEqual(directory(6), directory(5))


if __name__ == "__main__":
    unittest.main()
