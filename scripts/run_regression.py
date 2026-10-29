"""Identical local/CI RTL regression, with source fingerprints and per-step logs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def capture(command):
    try:
        r = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-revision", default="unspecified")
    args = parser.parse_args()
    reports = ROOT / "build/reports"
    reports.mkdir(parents=True, exist_ok=True)
    sources = []
    for directory in ("rtl", "tests", "scripts", "model", ".github"):
        sources.extend(p for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    sources.extend([ROOT / "Makefile", ROOT / "requirements-test.txt"])
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)}
    import numpy
    environment = dict(base_revision=args.base_revision,
                       tested_revision=os.getenv("GITHUB_SHA") or capture(["git", "rev-parse", "HEAD"]),
                       python=sys.version, numpy=numpy.__version__, platform=platform.platform(),
                       verilator=capture(["verilator", "--version"]), compiler=capture(["g++", "--version"]),
                       source_sha256=hashes)
    (reports / "environment.json").write_text(json.dumps(environment, indent=2), encoding="utf-8")
    phases = [
        ("lint", ["make", "lint", "lint-integration"]),
        ("lint-compatibility", [sys.executable, "-m", "unittest", "tests.check_verilator_compatibility", "-v"]),
        ("python", ["make", "test-model", f"PYTHON={sys.executable}"]),
        ("monitor", ["make", "test-monitor"]),
        ("compute", ["make", "build-compute"]),
        ("core-directed", [sys.executable, "scripts/run_core_tests.py"]),
        ("core-golden", [sys.executable, "scripts/verify_b_vectors.py"]),
        ("failure-replay", [sys.executable, "scripts/check_failure_replay.py"]),
        ("adapter-build", ["make", "build-adapter"]),
        ("adapter", [sys.executable, "scripts/run_adapter_tests.py"]),
        ("integration-build", ["make", "build-integration", "build-integration16"]),
        ("integration", [sys.executable, "scripts/verify_b_vectors.py", "--integration"]),
        ("integration16", [sys.executable, "scripts/verify_b_vectors.py", "--integration", "--integration-lanes", "16"]),
        ("lane-benchmark", [sys.executable, "scripts/benchmark_lanes.py"]),
        ("board-mem", [sys.executable, "scripts/verify_board_mem.py"]),
        ("b-board-control", ["make", "lint-lane-adapter", "test-lane-adapter",
                             "lint-control", "lint-control-16", "test-system-control",
                             "lint-fixed-slice", "test-fixed-slice",
                             "lint-fixed-slice-qwen", "test-fixed-slice-qwen", f"PYTHON={sys.executable}"]),
        ("uart-readback", ["make", "lint-result-capture", "test-result-capture",
                           "lint-fixed-slice-qwen-uart", "lint-uart-board",
                           "test-uart-board", "test-uart-board-overflow",
                           "lint-fixed-slice-qwen-multigroup", "test-fixed-slice-qwen-multigroup"]),
        ("uart-parser", [sys.executable, "-m", "unittest", "tests.test_uart_readback"]),
        ("a-multigroup-uart", ["make", "lint-a-multigroup-uart", "test-a-multigroup-uart",
                               f"PYTHON={sys.executable}"]),
        ("a-multigroup-pds", ["make", "lint-a-multigroup-pds", "test-a-multigroup-pds",
                              f"PYTHON={sys.executable}"]),
    ]
    results = []
    for name, command in phases:
        print(f"RUN {name}: {' '.join(command)}", flush=True)
        log = reports / f"{name}.log"
        with log.open("w", encoding="utf-8") as stream:
            try:
                code = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=1200).returncode
            except subprocess.TimeoutExpired:
                stream.write("\nPHASE TIMEOUT after 1200 seconds\n")
                code = 124
            except OSError as exc:
                stream.write(str(exc))
                code = 127
        results.append(dict(phase=name, command=command, returncode=code, log=str(log.relative_to(ROOT))))
        (reports / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"{'PASS' if code == 0 else 'FAIL'} {name}", flush=True)
        if code:
            print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]), file=sys.stderr)
            raise SystemExit(1)
    print(f"PASS REGRESSION phases={len(results)} reports={reports}", flush=True)


if __name__ == "__main__":
    main()
