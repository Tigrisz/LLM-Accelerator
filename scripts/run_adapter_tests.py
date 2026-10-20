"""Run split-beat protocol tests with automatic failure waveform replay."""
from pathlib import Path
from sim_runner import run_simulation

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    run_simulation([str(ROOT / "build/adapter16/Vpaired_lane_adapter")],
                   cwd=ROOT, label="adapter16-directed")
