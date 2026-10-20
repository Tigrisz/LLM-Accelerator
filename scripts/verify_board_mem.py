"""Independently check and stage a fixed-slice ROM image."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "fpgatest/qwen_slice/prj/mem"
DEFAULT_TARGET = ROOT / "build/fixed_slice_qwen"


def read_words(source: Path, name: str, width: int, count: int) -> list[int]:
    lines = (source / name).read_text(encoding="ascii").splitlines()
    if len(lines) != count or any(len(line.strip()) != width // 4 for line in lines):
        raise ValueError(f"{name}: unexpected word count/width")
    return [int(line, 16) for line in lines]


def signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def verify_slice(source: Path, target: Path) -> dict:
    config_path = source / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        # The PDS project stores only the three ROM images.  Infer the v1
        # smoke dimensions so the original regression remains self-contained.
        activation_line_count = len((source / "activation.mem").read_text(encoding="ascii").splitlines())
        expected_line_count = len((source / "expected.mem").read_text(encoding="ascii").splitlines())
        config = {
            "format_version": 1,
            "source": "pds_mem_without_config",
            "N": expected_line_count,
            "K": activation_line_count * 32,
            "padded_K": activation_line_count * 32,
            "lanes": 32,
            "group_size": 128,
        }
    rows = int(config["N"])
    logical_k = int(config["K"])
    padded_k = int(config["padded_K"])
    group_size = int(config["group_size"])
    lanes = int(config.get("lanes", 32))
    if rows <= 0 or logical_k <= 0 or padded_k < logical_k:
        raise ValueError("invalid slice dimensions")
    if group_size != 128 or lanes != 32 or padded_k % group_size or padded_k % lanes:
        raise ValueError("board image requires group_size=128, lanes=32, and aligned padded_K")
    groups = padded_k // group_size
    weight_words = read_words(source, "weights.mem", 128, rows * padded_k // lanes)
    activation_words = read_words(source, "activation.mem", 256, padded_k // lanes)
    expected_words = read_words(source, "expected.mem", 32, rows * groups)
    x = [signed((word >> (8 * i)) & 255, 8) for word in activation_words for i in range(lanes)]
    w = [signed((word >> (4 * i)) & 15, 4) for word in weight_words for i in range(lanes)]
    calculated: list[int] = []
    for row in range(rows):
        row_base = row * padded_k
        for group in range(groups):
            start = group * group_size
            stop = start + group_size
            calculated.append(sum(w[row_base + k] * x[k] for k in range(start, stop)))
    expected = [signed(value, 32) for value in expected_words]
    if calculated != expected:
        raise ValueError(f"Board golden mismatch: calculated={calculated}, expected={expected}")

    target.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in ("weights.mem", "activation.mem", "expected.mem"):
        hashes[name] = hashlib.sha256((source / name).read_bytes()).hexdigest()
        if source.resolve() != target.resolve():
            shutil.copyfile(source / name, target / name)
    report = {
        "source": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
        "config": config,
        "sha256": hashes,
        "expected": expected,
        "calculated": calculated,
    }
    report_path = ROOT / "build/reports/board_mem.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    source = args.source if args.source.is_absolute() else ROOT / args.source
    target = args.target if args.target.is_absolute() else ROOT / args.target
    report = verify_slice(source, target)
    config = report["config"]
    print(
        f"PASS BOARD_MEM rows={config['N']} K={config['K']} "
        f"groups={config['padded_K'] // config['group_size']} "
        "independent_integer_golden=matched"
    )


if __name__ == "__main__":
    main()
