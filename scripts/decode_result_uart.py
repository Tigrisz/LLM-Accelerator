#!/usr/bin/env python3
"""Decode one result_capture_uart binary frame into JSON."""

import argparse
import json
from pathlib import Path


def decode(frame: bytes, source: str = "unknown") -> dict:
    if len(frame) < 9 or frame[:3] != bytes((0xA5, 0x5A, 0x01)):
        raise ValueError("invalid result frame header")
    count = int.from_bytes(frame[3:7], "little")
    expected_len = 7 + count * 8 + 2
    if len(frame) != expected_len or frame[-2:] != bytes((0x5A, 0xA5)):
        raise ValueError(f"invalid frame length/footer: got {len(frame)}, expected {expected_len}")
    records = []
    for index in range(count):
        offset = 7 + index * 8
        row_id = int.from_bytes(frame[offset:offset + 2], "little")
        group_id = int.from_bytes(frame[offset + 2:offset + 4], "little")
        partial_sum = int.from_bytes(frame[offset + 4:offset + 8], "little", signed=True)
        records.append({"index": index, "row_id": row_id,
                        "group_id": group_id, "partial_sum": partial_sum})
    if source not in ("board", "simulation", "unknown"):
        raise ValueError("invalid capture source")
    return {"source": source, "version": 1, "count": count, "records": records}


def verify_records(result: dict, golden: list, rows: int, groups: int) -> None:
    total = rows * groups
    if rows <= 0 or groups <= 0 or len(golden) != total or result["count"] != total:
        raise ValueError("capture/golden count does not match rows * groups")
    seen = set()
    for record in result["records"]:
        row, group = record["row_id"], record["group_id"]
        if not (0 <= row < rows and 0 <= group < groups) or (row, group) in seen:
            raise ValueError(f"duplicate or out-of-range tag ({row}, {group})")
        seen.add((row, group))
        want = int(golden[row * groups + group]) & 0xffffffff
        if record["partial_sum"] & 0xffffffff != want:
            raise ValueError(f"partial_sum mismatch at row={row}, group={group}")
    if len(seen) != total:
        raise ValueError("missing result tags")


class FrameScanner:
    """Recover a valid frame from UART chunks, noise or interrupted frames."""
    def __init__(self, max_records: int = 256):
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = max_records
        self.buffer = bytearray()

    def feed(self, chunk: bytes):
        self.buffer.extend(chunk)
        while True:
            start = self.buffer.find(b"\xa5\x5a\x01")
            if start < 0:
                # Preserve a split header across two serial reads.
                self.buffer = self.buffer[-2:]
                return None
            if start:
                del self.buffer[:start]
            if len(self.buffer) < 7:
                return None
            count = int.from_bytes(self.buffer[3:7], "little")
            if not 0 < count <= self.max_records:
                del self.buffer[0]
                continue
            size = 9 + 8 * count
            if len(self.buffer) < size:
                return None
            candidate = bytes(self.buffer[:size])
            try:
                decode(candidate)
            except ValueError:
                # A reset may leave a partial old frame before a complete
                # new frame already in this buffer. Rescan before reading.
                del self.buffer[0]
                continue
            del self.buffer[:size]
            return candidate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frame", type=Path, help="raw binary UART frame")
    parser.add_argument("--output", type=Path, help="write JSON to this file")
    parser.add_argument("--source", choices=("board", "simulation", "unknown"), default="unknown")
    parser.add_argument("--expected", type=Path, help="golden expected.mem, row-major group-major")
    parser.add_argument("--rows", type=int)
    parser.add_argument("--groups", type=int)
    args = parser.parse_args()
    decoded = decode(args.frame.read_bytes(), source=args.source)
    if args.expected is not None:
        if args.rows is None or args.groups is None:
            parser.error("--expected requires --rows and --groups")
        golden = [int(word, 16) for word in args.expected.read_text(encoding="ascii").split()]
        verify_records(decoded, golden, args.rows, args.groups)
        decoded["verification"] = {"passed": True, "rows": args.rows, "groups": args.groups}
    result = json.dumps(decoded, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
