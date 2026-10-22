"""Audit a Task-A integer fixture and stage ROM words for B's 32-to-16 path."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.stream_reference import iter_gemv_beats


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _mem_bytes(data: bytes, width: int) -> bytes:
    words = [f"{int.from_bytes(data[p:p + width], 'little'):0{width * 2}x}"
             for p in range(0, len(data), width)]
    return ("\n".join(words) + "\n").encode("ascii")


def prepare_case(source: Path, output: Path) -> dict:
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("output must not overwrite or contain the source fixture")
    names = ("config.json", "weight_packed.bin", "activation_int8.bin",
             "expected_partial.npy", "scales.npy", "stream_reference.json",
             "capture.json", "comparison.json")
    raw = {name: (source / name).read_bytes() for name in names}
    config = json.loads(raw["config.json"])
    for key in ("format_version", "N", "K", "padded_K", "group_size", "lanes"):
        if type(config.get(key)) is not int:
            raise ValueError(f"config {key} must be an integer")
    n, k, padded, lanes = (config[key] for key in ("N", "K", "padded_K", "lanes"))
    if config["format_version"] != 1 or config["group_size"] != 128:
        raise ValueError("requires format_version=1 and group_size=128")
    if lanes not in (16, 32):
        raise ValueError("source lanes must be 16 or 32")
    if not 0 < n <= 65535 or k <= 0 or padded != ((k + 127) // 128) * 128:
        raise ValueError("invalid dimensions or padding")
    groups = padded // 128
    if groups > 65535:
        raise ValueError("group tags exceed 16 bits")
    weights, activation = raw["weight_packed.bin"], raw["activation_int8.bin"]
    if len(weights) != n * padded // 2 or len(activation) != padded:
        raise ValueError("packed input length does not match N/padded_K")
    x = [value - 256 if value >= 128 else value for value in activation]
    w = [value - 16 if value >= 8 else value
         for byte in weights for value in (byte & 15, byte >> 4)]
    rows = [w[row * padded:(row + 1) * padded] for row in range(n)]
    if any(x[k:]) or any(any(row[k:]) for row in rows):
        raise ValueError("nonzero tail padding")
    expected = np.load(source / "expected_partial.npy", allow_pickle=False)
    if expected.dtype.kind != "i" or expected.dtype.itemsize != 4:
        raise ValueError("golden must be signed INT32")
    if expected.shape != (n, groups):
        raise ValueError("golden shape does not match row/group dimensions")
    calculated = [[sum(row[i] * x[i] for i in range(g * 128, (g + 1) * 128))
                   for g in range(groups)] for row in rows]
    if calculated != expected.tolist():
        raise ValueError("independent integer golden mismatch")
    scales = np.load(source / "scales.npy", allow_pickle=False)
    if scales.shape != (n, groups) or not np.isfinite(scales).all() or not (scales > 0).all():
        raise ValueError("invalid scale shape/values")
    supplied_stream = json.loads(raw["stream_reference.json"])
    reference_stream = list(iter_gemv_beats([row[:k] for row in rows], x[:k], lanes, 128))
    if supplied_stream != reference_stream:
        raise ValueError("source lane stream does not match packed input/metadata")
    capture = json.loads(raw["capture.json"])
    if (capture.get("format_version") != 1 or capture.get("source") != "simulation"
            or capture.get("completed") is not True):
        raise ValueError("reference capture must be a completed simulation")
    records = capture.get("results")
    if not isinstance(records, list) or len(records) != n * groups:
        raise ValueError("reference capture count mismatch")
    for index, record in enumerate(records):
        if (not isinstance(record, dict)
                or any(type(record.get(key)) is not int
                       for key in ("row_id", "group_id", "partial_sum"))
                or (record["row_id"], record["group_id"], record["partial_sum"])
                != (index // groups, index % groups, calculated[index // groups][index % groups])):
            raise ValueError("reference capture tag/order/value mismatch")
    comparison = json.loads(raw["comparison.json"])
    if (comparison.get("status") != "pass"
            or comparison.get("golden_sha256") != hashlib.sha256(raw["expected_partial.npy"]).hexdigest()
            or comparison.get("capture_sha256") != hashlib.sha256(raw["capture.json"]).hexdigest()):
        raise ValueError("reference capture comparison/hash mismatch")

    board_config = {**config, "source": "task_a_synthetic",
                    "source_lanes": lanes, "compute_lanes": 16,
                    "rom_pack_lanes": 32, "lanes": 32}
    expected_words = ("\n".join(f"{v & 0xffffffff:08x}"
                                for row in calculated for v in row) + "\n").encode("ascii")
    staged = {"weights.mem": _mem_bytes(weights, 16),
              "activation.mem": _mem_bytes(activation, 32),
              "expected.mem": expected_words, "config.json": _json_bytes(board_config)}
    label = source.relative_to(ROOT).as_posix() if source.is_relative_to(ROOT) else source.name
    report = {
        "format_version": 1, "fixture": label, "input_kind": "task_a_synthetic",
        "source_capture": "simulation", "board_verified": False,
        "N": n, "K": k, "padded_K": padded, "group_size": 128, "groups": groups,
        "source_lanes": lanes, "compute_lanes": 16, "rom_pack_lanes": 32,
        "expected_records": n * groups, "uart_frame_bytes": 9 + 8 * n * groups,
        "source_stream_beats": len(supplied_stream), "independent_integer_golden": "matched",
        "input_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()},
        "output_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in staged.items()},
    }
    staged["manifest.json"] = _json_bytes(report)
    # Validate every destination before writing any file, and allow only
    # byte-identical reruns. A wrong output path must not clobber a baseline.
    for name, data in staged.items():
        dest = output / name
        if dest.exists() and (not dest.is_file() or dest.read_bytes() != data):
            raise ValueError(f"refusing to overwrite different output: {dest}")
    output.mkdir(parents=True, exist_ok=True)
    for name, data in staged.items():
        if not (output / name).exists():
            with (output / name).open("xb") as stream:
                stream.write(data)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = prepare_case(args.source, args.output)
    print(f"PASS CAPTURE_CASE N={report['N']} K={report['K']} "
          f"records={report['expected_records']} source_lanes={report['source_lanes']} "
          "rom_pack_lanes=32 board_verified=false")


if __name__ == "__main__":
    main()
