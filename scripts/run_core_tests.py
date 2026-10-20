"""Run both core widths, preserving failure logs and VCD replay evidence."""
from pathlib import Path
from sim_runner import run_simulation

ROOT = Path(__file__).resolve().parents[1]
for lanes in (16, 32):
    run_simulation([ROOT / f"build/core_{lanes}/Vgemv_core"], cwd=ROOT,
                   label=f"core-directed-{lanes}")
