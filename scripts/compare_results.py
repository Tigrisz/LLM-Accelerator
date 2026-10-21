"""Compare one tagged result capture against MEM or NPY INT32 golden data."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys


def integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label}: expected integer in [{minimum}, {maximum}]")
    return value


def int32(value):
    if isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{8}", value):
        raw = int(value, 16)
        return raw - 2**32 if raw >= 2**31 else raw
    return integer(value, "partial_sum", -(2**31), 2**31-1)


def golden_values(path, rows=None, groups=None):
    if path.suffix == ".npy":
        import numpy as np
        array = np.load(path, allow_pickle=False)
        if array.ndim != 2 or array.dtype.kind != "i" or array.dtype.itemsize != 4 or not array.size:
            raise ValueError("NPY golden must be a nonempty 2D signed INT32 array")
        if rows is not None and rows != array.shape[0] or groups is not None and groups != array.shape[1]:
            raise ValueError("NPY dimensions disagree with --rows/--groups")
        return array.astype(object).tolist()
    if path.suffix != ".mem":
        raise ValueError("golden extension must be .mem or .npy")
    integer(rows, "rows", 1, 65536)
    integer(groups, "groups", 1, 65536)
    words = path.read_text(encoding="utf-8").split()
    if len(words) != rows*groups or any(not re.fullmatch(r"[0-9a-fA-F]{8}", w) for w in words):
        raise ValueError("MEM golden requires rows*groups eight-digit hex words, row-major")
    values = [int32("0x"+word) for word in words]
    return [values[row*groups:(row+1)*groups] for row in range(rows)]


def compare(expected, capture):
    if not isinstance(capture, dict) or type(capture.get("format_version")) is not int or capture["format_version"] != 1:
        raise ValueError("capture format_version must be 1")
    if capture.get("source") not in ("board", "simulation", "synthetic"):
        raise ValueError("source must be board, simulation or synthetic")
    if not isinstance(capture.get("run_id"), str) or not capture["run_id"].strip():
        raise ValueError("nonempty run_id required")
    if type(capture.get("completed")) is not bool or not isinstance(capture.get("results"), list):
        raise ValueError("completed boolean and results list required")
    rows, groups = len(expected), len(expected[0])
    seen = set()
    errors, counts = [], Counter()

    def error(kind, **details):
        counts[kind] += 1
        if len(errors) < 100:
            errors.append(dict(kind=kind, **details))

    if not capture["completed"]:
        error("incomplete_capture")
    for index, record in enumerate(capture["results"]):
        if not isinstance(record, dict) or set(record) != {"row_id", "group_id", "partial_sum"}:
            raise ValueError(f"record {index}: requires exactly row_id, group_id, partial_sum")
        row = integer(record["row_id"], f"record {index} row_id", 0, 65535)
        group = integer(record["group_id"], f"record {index} group_id", 0, 65535)
        actual = int32(record["partial_sum"])
        key = row, group
        if row >= rows or group >= groups:
            error("unexpected_tag", index=index, row_id=row, group_id=group)
            continue
        if key in seen:
            error("duplicate", index=index, row_id=row, group_id=group)
        seen.add(key)
        if index >= rows*groups or key != (index//groups, index%groups):
            error("order", index=index, row_id=row, group_id=group)
        if actual != expected[row][group]:
            error("value", index=index, row_id=row, group_id=group,
                  expected=expected[row][group], actual=actual, delta=actual-expected[row][group])
    for row in range(rows):
        for group in range(groups):
            if (row, group) not in seen:
                error("missing", row_id=row, group_id=group)
    return dict(status="pass" if not counts else "mismatch", source=capture["source"],
                run_id=capture["run_id"], expected_count=rows*groups,
                received_count=len(capture["results"]), error_counts=dict(counts),
                first_error=errors[0] if errors else None, errors=errors,
                errors_truncated=sum(counts.values()) > len(errors))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_capture(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_pairs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", required=True, type=Path)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--rows", type=int)
    parser.add_argument("--groups", type=int)
    parser.add_argument("--bitstream", type=Path,
                        help="Require capture bitstream_sha256 to match this file")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.report.resolve() in {p.resolve() for p in (args.golden, args.capture, args.bitstream) if p}:
        parser.error("report must not overwrite an input")
    try:
        expected = golden_values(args.golden, args.rows, args.groups)
        capture = load_capture(args.capture)
        report = compare(expected, capture)
        report["golden_sha256"] = sha256(args.golden)
        report["capture_sha256"] = sha256(args.capture)
        if args.bitstream:
            digest = sha256(args.bitstream)
            claimed = capture.get("bitstream_sha256")
            if not isinstance(claimed, str) or claimed.lower() != digest:
                raise ValueError("capture bitstream_sha256 missing or differs from supplied bitstream")
            report["bitstream_sha256"] = digest
        code = 0 if report["status"] == "pass" else 1
    except (OSError, ValueError, TypeError) as exc:
        report = dict(status="input_error", message=str(exc))
        code = 2
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "errors"}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
