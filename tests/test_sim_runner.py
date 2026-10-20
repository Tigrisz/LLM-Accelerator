"""Check that failure evidence survives nonzero exit, timeout, and successful replay."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from sim_runner import run_simulation


class SimulationRunnerTests(unittest.TestCase):
    def test_original_failure_not_hidden_by_successful_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            fake = path / "fake.py"
            fake.write_text("import os,sys,pathlib\np=os.getenv('TRACE_FILE')\n"
                            "if p: pathlib.Path(p).write_text('synthetic test trace')\n"
                            "print('seed=123 cycle=7')\nsys.exit(0 if p else 5)\n")
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                run_simulation([sys.executable, fake], cwd=path, label="injected", failure_root=path / "failures")
            report = json.loads((path / "failures/injected/reproduce.json").read_text())
            self.assertEqual(report["original_returncode"], 5)
            self.assertEqual(report["replay_returncode"], 0)
            self.assertTrue(report["trace_created"])
            self.assertIn("seed=123", (path / "failures/injected/original.log").read_text())

    def test_timeout_is_failure_with_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            with self.assertRaises(RuntimeError):
                run_simulation([sys.executable, "-c", "import time; time.sleep(5)"], cwd=path,
                               label="timeout", failure_root=path / "failures", timeout=0.1)
            report = json.loads((path / "failures/timeout/reproduce.json").read_text())
            self.assertEqual(report["original_returncode"], 124)

    def test_success_does_not_create_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            run_simulation([sys.executable, "-c", "pass"], cwd=path, label="ok", failure_root=path / "failures")
            self.assertFalse((path / "failures").exists())
