"""Convert a K=128 model-slice fixture into FPGA ROM initialization files."""

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
    if config["K"] != 128 or config["padded_K"] != 128 or config["group_size"] != 128:
        raise ValueError("fixed_slice_runner v1 requires K=padded_K=group_size=128")
    n = int(config["N"])
    weights = (source / "weight_packed.bin").read_bytes()
    activation = (source / "activation_int8.bin").read_bytes()
    expected = np.load(source / "expected_partial.npy", allow_pickle=False)
    if len(weights) != n * 64 or len(activation) != 128 or expected.shape != (n, 1):
        raise ValueError("slice files do not match N x 128 fixed-runner shape")
    output.mkdir(parents=True, exist_ok=True)
    write_words(weights, 16, output / "weights.mem")
    write_words(activation, 32, output / "activation.mem")
    (output / "expected.mem").write_text(
        "\n".join(f"{int(value) & 0xffffffff:08x}" for value in expected[:, 0]) + "\n",
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
