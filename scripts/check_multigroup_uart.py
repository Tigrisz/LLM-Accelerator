"""Run the B UART RTL on Task-A fixtures; all generated captures are simulation."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import uuid

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from decode_result_uart import decode, verify_records


def save_json(path: Path, value: dict):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes((json.dumps(value, indent=2) + "\n").encode("utf-8"))
    temporary.replace(path)


def main():
    report_root = ROOT / "build/reports/a_multigroup"
    report_root.mkdir(parents=True, exist_ok=True)
    attempt_id = uuid.uuid4().hex
    attempt_root = report_root / "runs" / attempt_id
    attempt_root.mkdir(parents=True)
    summary = {"source": "simulation", "board_verified": False,
               "attempt_id": attempt_id, "status": "running", "cases": []}

    def publish():
        save_json(attempt_root / "summary.json", summary)
        save_json(report_root / "summary.json", summary)

    publish()
    try:
        results, hashes = run_cases(attempt_root, attempt_id)
    except BaseException as exc:
        summary.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        publish()
        raise
    summary.update(status="pass", cases=results, source_sha256=hashes)
    publish()


def run_cases(attempt_root: Path, attempt_id: str):
    results = []
    for k in (256, 384):
        case = f"lanes16_n3_k{k}"
        source = ROOT / "tests/fixtures/a_multigroup" / case
        groups, total = k // 128, 3 * (k // 128)
        golden = np.load(source / "expected_partial.npy", allow_pickle=False).reshape(-1).tolist()
        a_reference = json.loads((source / "capture.json").read_text())
        for overflow in (False, True):
            depth = total - int(overflow)
            output = attempt_root / case / ("overflow" if overflow else "complete")
            output.mkdir(parents=True, exist_ok=True)
            command = ["make", "--no-print-directory", "run-a-multigroup-uart-case",
                       f"A_CAPTURE_K={k}", f"A_CAPTURE_DEPTH={depth}",
                       f"A_CAPTURE_REPORT_DIR={output.relative_to(ROOT).as_posix()}",
                       f"PYTHON={sys.executable}"]
            with (output / "simulation.log").open("w", encoding="utf-8") as log:
                result = subprocess.run(command, cwd=ROOT, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=240)
            if result.returncode:
                print("\n".join((output / "simulation.log").read_text().splitlines()[-35:]),
                      file=sys.stderr)
                raise SystemExit(result.returncode)
            frames = []
            for run in (1, 2, 3):
                frame = (output / f"sim_run{run}.bin").read_bytes()
                decoded = decode(frame, source="simulation")
                if not overflow:
                    verify_records(decoded, golden, 3, groups)
                if decoded["count"] != depth:
                    raise ValueError("simulation count does not match capture depth")
                for index, record in enumerate(decoded["records"]):
                    want = (index // groups, index % groups, golden[index])
                    got = (record["row_id"], record["group_id"], record["partial_sum"])
                    if got != want:
                        raise ValueError(f"tag/order/value mismatch: {got}, expected {want}")
                decoded["verification"] = {
                    "complete": not overflow, "expected_overflow": overflow,
                    "prefix_matches_golden": True, "rows": 3, "groups": groups,
                }
                save_json(output / f"sim_run{run}.json", decoded)
                if not overflow:
                    a_format = {
                        "format_version": 1, "source": "simulation",
                        "run_id": f"b-fixed-runner-{case}-{attempt_id}-reset{run}",
                        "results": [{key: value for key, value in item.items() if key != "index"}
                                    for item in decoded["records"]],
                        "completed": True,
                    }
                    if a_format["results"] != a_reference["results"]:
                        raise ValueError("B UART values differ from original A RTL capture")
                    save_json(output / f"sim_run{run}_a_format.json", a_format)
                frames.append(frame)
            if not frames[0] == frames[1] == frames[2]:
                raise ValueError("reset reruns are not byte-identical")
            entry = {"case": case, "source": "simulation", "board_verified": False,
                     "records": depth, "uart_bytes": len(frames[0]),
                     "resets": 3, "mid_tx_reset": True, "expected_overflow": overflow,
                     "comparison": "pass", "frame_sha256": hashlib.sha256(frames[0]).hexdigest(),
                     "golden_sha256": hashlib.sha256((source / "expected_partial.npy").read_bytes()).hexdigest(),
                     "simulation_log": (output / "simulation.log").relative_to(ROOT).as_posix()}
            results.append(entry)
            print(f"PASS A_UART_SIM K={k} records={depth} bytes={len(frames[0])} "
                  f"resets=3 mid_tx_reset=1 expected_overflow={int(overflow)}", flush=True)
    sources = list((ROOT / "rtl").rglob("*.sv")) + [
        ROOT / "tests/tb_multigroup_uart_board.sv",
        ROOT / "tests/test_multigroup_uart_board.cpp", ROOT / "tests/uart_test_decoder.h",
        ROOT / "tests/test_capture_case.py", ROOT / "tests/test_multigroup_report.py",
        ROOT / "scripts/prepare_capture_case.py", ROOT / "scripts/check_multigroup_uart.py",
        ROOT / "Makefile",
    ]
    return results, {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(sources)}


if __name__ == "__main__":
    main()
