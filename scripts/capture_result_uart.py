#!/usr/bin/env python3
"""Passively save one board UART frame; never send model data or commands."""
import argparse
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-records", type=int, default=256)
    args = parser.parse_args()
    if args.timeout <= 0 or args.max_records <= 0:
        parser.error("timeout and max-records must be positive")
    if args.output.exists():
        parser.error("output already exists; choose a new filename for each reset run")
    try:
        import serial
    except ImportError:
        parser.error("pyserial is required: install it in your Python virtual environment")
    from decode_result_uart import FrameScanner

    receiver = serial.Serial(port=None, baudrate=115200, bytesize=8,
                             parity="N", stopbits=1, timeout=0.2,
                             xonxoff=False, rtscts=False, dsrdtr=False)
    receiver.dtr = False
    receiver.rts = False
    receiver.port = args.port
    scanner = FrameScanner(max_records=args.max_records)
    deadline = time.monotonic() + args.timeout
    with receiver:
        print("UART opened. Press KEY0 to reset/re-run the FPGA now.", flush=True)
        while time.monotonic() < deadline:
            frame = scanner.feed(receiver.read(4096))
            if frame is not None:
                count = int.from_bytes(frame[3:7], "little")
                size = len(frame)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("xb") as stream:
                    stream.write(frame)
                print(f"CAPTURED BOARD records={count} bytes={size} file={args.output}")
                return
    raise SystemExit("UART timeout: no complete frame received; no board PASS claimed")


if __name__ == "__main__":
    main()
