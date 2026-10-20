"""Export the deterministic case used by the system-control BFM."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_b_vectors import export_case


if __name__ == "__main__":
    source = ROOT / "tests" / "vectors" / "case_n3_k256"
    destination = ROOT / "build" / "b_fixtures" / "case_n3_k256.txt"
    export_case(source, destination)
    print(destination)
