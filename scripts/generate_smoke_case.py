"""Generate the canonical Day 4 small case used for task A integration."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model.gen_vectors import generate_case  # noqa: E402


if __name__ == "__main__":
    output = ROOT / "tests" / "vectors" / "case_001"
    config = generate_case(output, rows=3, cols=256, lanes=32, group_size=128, seed=1)
    print(f"generated {output}")
    print(config)

