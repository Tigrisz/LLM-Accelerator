"""Generate the three task-A handoff cases requested by the project plan."""

from __future__ import annotations

import sys
from pathlib import Path

# Make direct invocation (`python scripts/generate_requested_vectors.py`) use
# the repository root just like the other project scripts.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model.gen_vectors import generate_case


CASES = (
    ("case_n1_k128", 1, 128, 101),
    ("case_n3_k256", 3, 256, 302),
    ("case_n2_k129", 2, 129, 2129),
)


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "tests" / "vectors"
    for name, rows, cols, seed in CASES:
        output = root / name
        config = generate_case(output, rows=rows, cols=cols, lanes=32, group_size=128, seed=seed)
        print(f"{output}: N={config['N']} K={config['K']} padded_K={config['padded_K']}")


if __name__ == "__main__":
    main()
