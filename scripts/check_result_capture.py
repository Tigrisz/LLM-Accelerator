"""Exercise result comparison with results actually produced by RTL."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    capture = ROOT / "build/reports/qwen_simulation_capture.json"
    capture.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RESULT_CAPTURE=str(capture))
    subprocess.run([str(ROOT / "build/fixed_slice_qwen_sim/Vtb_fixed_slice_qwen")],
                   cwd=ROOT, env=env, check=True, timeout=60)
    subprocess.run([sys.executable, str(ROOT/"scripts/compare_results.py"),
                    "--golden", str(ROOT/"build/fixed_slice_qwen/expected.mem"),
                    "--rows", "16", "--groups", "1", "--capture", str(capture),
                    "--report", str(ROOT/"build/reports/qwen_simulation_comparison.json")],
                   cwd=ROOT, check=True, timeout=60)


if __name__ == "__main__":
    main()
