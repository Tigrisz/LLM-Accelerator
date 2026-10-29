"""Explicit RTL regression gate; kept outside the Python-only test discovery."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VerilatorCompatibilityTests(unittest.TestCase):
    def test_every_lint_target_on_selected_simulator(self):
        simulator = os.environ.get("VERILATOR", "verilator")
        self.assertIsNotNone(shutil.which(simulator), "Verilator is required; do not skip compatibility checks")
        version = subprocess.run([simulator, "--version"], capture_output=True, text=True, timeout=15)
        self.assertEqual(version.returncode, 0, version.stderr)
        targets = list(dict.fromkeys(re.findall(r"^(lint(?:-[a-z0-9]+)*):", (ROOT / "Makefile").read_text(), re.MULTILINE)))
        self.assertIn("lint-fixed-slice-qwen-uart", targets)
        for target in targets:
            with self.subTest(target=target, simulator=version.stdout.strip()):
                result = subprocess.run(["make", target, "VERILATOR=" + simulator, "PYTHON=" + sys.executable],
                                        cwd=ROOT, capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode, 0,
                                 version.stdout + "\n" + target + "\n" + (result.stdout + result.stderr)[-12000:])


if __name__ == "__main__":
    unittest.main()
