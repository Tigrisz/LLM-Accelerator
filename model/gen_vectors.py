"""Generate deterministic W4A8 GEMV test cases for RTL and Python tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

try:
    from .golden_gemv import gemv_partial_sums
    from .pack_weights import pack_weight_matrix
    from .stream_reference import iter_gemv_beats
except ImportError:  # direct script execution from the repository root
    from golden_gemv import gemv_partial_sums
    from pack_weights import pack_weight_matrix
    from stream_reference import iter_gemv_beats


def generate_case(
    output_dir: Path,
    rows: int,
    cols: int,
    lanes: int = 32,
    group_size: int = 128,
    seed: int = 1,
) -> dict:
    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive")
    if lanes <= 0 or group_size <= 0 or group_size % lanes:
        raise ValueError("lanes must be positive and divide group_size")
    rng = np.random.default_rng(seed)
    weights = rng.integers(-8, 8, size=(rows, cols), dtype=np.int8)
    activation = rng.integers(-128, 128, size=(cols,), dtype=np.int16).astype(np.int8)
    padded_cols = ((cols + group_size - 1) // group_size) * group_size
    activation_padded = np.zeros((padded_cols,), dtype=np.int8)
    activation_padded[:cols] = activation
    weights_list = weights.astype(np.int16).tolist()
    activation_list = activation.astype(np.int16).tolist()
    expected = np.asarray(gemv_partial_sums(weights_list, activation_list, group_size), dtype=np.int32)

    output_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "format_version": 1,
        "N": rows,
        "K": cols,
        "padded_K": padded_cols,
        "lanes": lanes,
        "group_size": group_size,
        "seed": seed,
        "weight_layout": "row-major, padded per row to group_size",
        "activation_layout": "signed INT8, logical order, zero-padded to padded_K",
    }
    (output_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (output_dir / "weight_packed.bin").write_bytes(pack_weight_matrix(weights_list, group_size))
    # The physical stream is group-padded.  K remains the logical length in
    # config.json; the tail bytes are explicit zero activations for RTL.
    (output_dir / "activation_int8.bin").write_bytes(activation_padded.tobytes())
    np.save(output_dir / "expected_partial.npy", expected)
    # Scales are one for synthetic integer vectors. This keeps the case useful
    # to RTL while preserving the same file shape as a quantized model case.
    groups = (cols + group_size - 1) // group_size
    np.save(output_dir / "scales.npy", np.ones((rows, groups), dtype=np.float32))
    stream = list(iter_gemv_beats(weights_list, activation_list, lanes, group_size))
    (output_dir / "stream_reference.json").write_text(
        json.dumps(stream, indent=2) + "\n", encoding="utf-8"
    )
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--cols", type=int, default=256)
    parser.add_argument("--lanes", type=int, default=32)
    parser.add_argument("--group-size", type=int, default=128)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    config = generate_case(args.output, args.rows, args.cols, args.lanes, args.group_size, args.seed)
    print(json.dumps(config, sort_keys=True))


if __name__ == "__main__":
    main()

