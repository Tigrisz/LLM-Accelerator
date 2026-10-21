"""Export real multi-group RTL handshakes and check the v1 capture CLI end to end."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys

from verify_b_vectors import ROOT, export_case, generate_case
from compare_results import sha256
from sim_runner import run_simulation


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def check_capture(golden, capture, report, code=0, kind=None):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/compare_results.py"),
         "--golden", str(golden), "--capture", str(capture), "--report", str(report)],
        cwd=ROOT, capture_output=True, text=True, timeout=60)
    if result.returncode != code:
        raise RuntimeError(f"{capture}: expected exit {code}, got {result.returncode}\n"
                           f"{result.stdout}\n{result.stderr}")
    data = json.loads(report.read_text())
    if kind and not data.get("error_counts", {}).get(kind):
        raise RuntimeError(f"{capture}: missing expected error category {kind}: {data}")
    if code == 2 and data["status"] != "input_error":
        raise RuntimeError(f"{capture}: expected input_error")
    return data


def main():
    root = ROOT / "build/reports/multigroup"
    root.mkdir(parents=True, exist_ok=True)
    summary = dict(status="running", source="simulation", input_source="synthetic",
                   cases=[], negative_checks=[])
    summary_path = root / "summary.json"
    write_json(summary_path, summary)
    for lanes in (16, 32):
        for k in (129, 255, 256, 257, 383, 384, 385):
            name = f"lanes{lanes}_n3_k{k}"
            folder = root / name
            cfg = generate_case(folder, 3, k, lanes=lanes, seed=k)
            fixture = export_case(folder, folder / "fixture.txt")
            binary = ROOT / "build" / ("integration16" if lanes == 16 else "integration") / "Vtb_b_integration"
            capture, report = folder / "capture.json", folder / "comparison.json"
            # Remove a previous run's output before launching the simulator.
            capture.unlink(missing_ok=True)
            run_simulation([binary, fixture, "--capture", capture], cwd=ROOT, label=name)
            golden = folder / "expected_partial.npy"
            data = check_capture(golden, capture, report)
            actual = json.loads(capture.read_text())
            if actual["source"] != "simulation" or data["received_count"] != 3 * (cfg["padded_K"] // 128):
                raise RuntimeError(f"{name}: invalid provenance/count")
            summary["cases"].append(dict(
                name=name, config=cfg, status=data["status"],
                count=data["received_count"], capture=f"{name}/capture.json",
                report=f"{name}/comparison.json",
                sha256={p.name: sha256(p) for p in
                        (fixture, golden, capture, folder / "config.json",
                         folder / "weight_packed.bin", folder / "activation_int8.bin")},
                simulator_sha256=sha256(binary)))
            # Corrupt actual RTL captures, never golden-as-capture. Each is explicitly synthetic.
            for fault, category in (
                ("value", "value"), ("missing", "missing"), ("duplicate", "duplicate"),
                ("order", "order"), ("tag", "unexpected_tag"),
                ("incomplete", "incomplete_capture"), ("format", None)):
                bad = copy.deepcopy(actual)
                bad["source"] = "synthetic"
                bad["run_id"] += f"-fault-{fault}"
                records = bad["results"]
                if fault == "value":
                    records[1]["partial_sum"] += 1
                elif fault == "missing":
                    records.pop(1)
                elif fault == "duplicate":
                    records.insert(1, copy.deepcopy(records[0]))
                elif fault == "order":
                    records[0], records[1] = records[1], records[0]
                elif fault == "tag":
                    records[1]["group_id"] = cfg["padded_K"] // 128
                elif fault == "incomplete":
                    bad["completed"] = False
                else:
                    records[1]["partial_sum"] = "invalid"
                bad_path = folder / f"fault_{fault}.json"
                bad_report = folder / f"fault_{fault}_report.json"
                write_json(bad_path, bad)
                code = 2 if fault == "format" else 1
                check_capture(golden, bad_path, bad_report, code, category)
                summary["negative_checks"].append(dict(
                    case=name, fault=fault, expected_exit=code, status="pass",
                    report=f"{name}/{bad_report.name}"))
            write_json(summary_path, summary)
    summary["status"] = "pass"
    write_json(summary_path, summary)
    print(f"PASS MULTIGROUP_CAPTURE cases={len(summary['cases'])} "
          f"negative_checks={len(summary['negative_checks'])} report={summary_path}")


if __name__ == "__main__":
    main()
