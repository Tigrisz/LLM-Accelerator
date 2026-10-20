"""Convert a model-slice fixture into FPGA ROM initialization files.

The ROM images use the same row-major, group-major order as the stream
reference: all beats for row 0/group 0, then row 0/group 1, followed by the
next row.  The fixed-slice runner consumes one 128-element group at a time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def write_words(data: bytes, word_bytes: int, path: Path) -> None:
    if len(data) % word_bytes:
        raise ValueError(f"{path.name} is not aligned to {word_bytes} bytes")
    lines = [f"{int.from_bytes(data[pos:pos + word_bytes], 'little'):0{word_bytes * 2}x}"
             for pos in range(0, len(data), word_bytes)]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def prepare(source: Path, output: Path) -> dict:
    config = json.loads((source / "config.json").read_text(encoding="utf-8"))
    n = int(config["N"])
    k = int(config["K"])
    padded_k = int(config["padded_K"])
    group_size = int(config["group_size"])
    lanes = int(config.get("lanes", 32))
    if n <= 0 or k <= 0 or padded_k < k:
        raise ValueError("slice dimensions must satisfy N>0 and padded_K>=K>0")
    if group_size != 128 or padded_k % group_size:
        raise ValueError("fixed_slice_runner requires group_size=128 and padded_K aligned to it")
    if lanes != 32 or group_size % lanes:
        raise ValueError("fixed_slice_runner memory images require lanes=32 and group_size divisible by lanes")
    groups = padded_k // group_size
    weights = (source / "weight_packed.bin").read_bytes()
    activation = (source / "activation_int8.bin").read_bytes()
    expected = np.load(source / "expected_partial.npy", allow_pickle=False)
    if len(weights) != n * padded_k // 2 or len(activation) != padded_k or expected.shape != (n, groups):
        raise ValueError("slice files do not match N x padded_K fixed-runner shape")
    output.mkdir(parents=True, exist_ok=True)
    write_words(weights, 16, output / "weights.mem")
    write_words(activation, 32, output / "activation.mem")
    (output / "expected.mem").write_text(
        "\n".join(f"{int(value) & 0xffffffff:08x}" for value in expected.reshape(-1)) + "\n",
        encoding="ascii",
    )
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
