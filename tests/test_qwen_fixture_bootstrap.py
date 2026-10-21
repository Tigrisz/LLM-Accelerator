"""A checkout without build/ must prepare both fixed-slice ROM fixtures."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class QwenFixtureBootstrapTests(unittest.TestCase):
    def check_target(self, target, variable, source, expected_counts):
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            output = Path(directory) / "absent_roms"
            result = subprocess.run(
                ["make", target, f"{variable}={output}", f"PYTHON={sys.executable}"],
                cwd=ROOT, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name, count in zip(
                    ("weights.mem", "activation.mem", "expected.mem"), expected_counts):
                data = (output / name).read_bytes()
                self.assertEqual(data, (ROOT / source / name).read_bytes())
                self.assertEqual(len(data.splitlines()), count)

    def test_legacy_k128_bootstraps_without_ignored_build_inputs(self):
        self.check_target(
            "fixed-slice-qwen-inputs", "FIXED_SLICE_QWEN_DIR",
            "tests/fixtures/qwen_n16_k128", (64, 4, 16),
        )

    def test_multigroup_bootstraps_from_committed_pds_roms(self):
        self.check_target(
            "fixed-slice-qwen-multigroup-inputs", "FIXED_SLICE_QWEN_MULTIGROUP_DIR",
            "fpgatest/qwen_slice/prj/mem", (1024, 64, 256),
        )


if __name__ == "__main__":
    unittest.main()
