"""Compare lanes with identical fixtures and deterministic memory settings."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys

from verify_b_vectors import export_case, generate_case
from sim_runner import run_simulation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/reports/lane_benchmark"
CASES = ((1, 128), (2, 129), (8, 2048), (2, 6144), (2, 8192))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Never leave a previous success report looking like this run's result.
    (OUT / "results.json").write_text(json.dumps({"status": "running"}))
    (OUT / "comparison.md").write_text("Benchmark in progress.\n")
    fixtures = {}
    for n, k in CASES:
        folder = ROOT / f"build/benchmark_vectors/n{n}_k{k}"
        generate_case(folder, n, k, seed=20261019)
        fixtures[n, k] = export_case(folder, folder / "fixture.txt")
    records = []
    for latency in (2, 20):
        for lanes in (16, 32):
            directory = f"build/benchmark_l{lanes}_d{latency}"
            command = ["make", "build-integration", f"INTEGRATION_LANES={lanes}",
                       f"INTEGRATION_DIR={directory}",
                       f"INTEGRATION_FLAGS=-GMEMORY_LATENCY={latency} -GMEMORY_RANDOM_STALL=0"]
            with (OUT / f"build_l{lanes}_d{latency}.log").open("w") as log:
                subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=300)
            for n, k in CASES:
                samples = []
                for repeat in range(2):
                    label = f"bench_l{lanes}_d{latency}_n{n}_k{k}_r{repeat}"
                    output = io.StringIO()
                    with redirect_stdout(output):
                        run_simulation([ROOT / directory / "Vtb_b_integration",
                                        fixtures[n, k], "--benchmark"], cwd=ROOT, label=label)
                    (OUT / f"{label}.log").write_text(output.getvalue())
                    lines = [line for line in output.getvalue().splitlines()
                             if line.startswith("PASS INTEGRATION ")]
                    if len(lines) != 1:
                        raise RuntimeError(f"Missing or ambiguous measurement: {label}")
                    metrics = {key: int(value) for key, value in re.findall(r"(\w+)=(\d+)", lines[0])}
                    padded = (k + 127) // 128 * 128
                    assert (metrics["lanes"], metrics["N"], metrics["K"]) == (lanes, n, k)
                    assert metrics["final_hold"] == metrics["random_output_stalls"] == metrics["output_wait"] == 0
                    assert metrics["input_beats"] == n * padded // lanes
                    assert metrics["groups"] == n * padded // 128
                    assert metrics["weight_bytes"] == n * padded // 2
                    assert metrics["cycles"] == sum(metrics[x] for x in ("input_beats", "input_wait", "input_blocked"))
                    samples.append(metrics)
                assert samples[0] == samples[1], "Non-deterministic benchmark"
                records.append(dict(**samples[0], memory_latency=latency,
                                    useful_mac_per_cycle=n*k/samples[0]["cycles"],
                                    padded_mac_per_cycle=n*padded/samples[0]["cycles"],
                                    weight_bytes_per_cycle=samples[0]["weight_bytes"]/samples[0]["cycles"]))
                print(f"PASS BENCH lanes={lanes} latency={latency} N={n} K={k} cycles={metrics['cycles']}", flush=True)
    sources = [p for directory in ("rtl", "tests", "scripts", "model")
               for p in (ROOT / directory).rglob("*")
               if p.suffix in (".sv", ".cpp", ".h", ".py") and "__pycache__" not in p.parts]
    sources.append(ROOT / "Makefile")
    report = dict(status="passed", repeats=2, records=records,
                  revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  python=sys.version,
                  verilator=subprocess.check_output(["verilator", "--version"], text=True).strip(),
                  source_sha256={p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                  fixture_sha256={f"n{n}_k{k}": hashlib.sha256(p.read_bytes()).hexdigest() for (n,k),p in fixtures.items()})
    (OUT / "results.json").write_text(json.dumps(report, indent=2))
    lines = ["# Deterministic lane comparison", "",
             "Cycles start immediately after the start-accepting edge and end at final output acceptance.",
             "Preload, start edge and post-completion checks are excluded. No random memory/output stalls or final hold.",
             "LATENCY is the memory model parameter, not total request latency. Each measurement repeats twice.",
             "MAC counts one multiply-accumulate as one operation. Padded work includes zero padding.", "",
             "| LATENCY | N | K | cycles16 | cycles32 | speedup16/32 | useful MAC/cycle16 | useful MAC/cycle32 |",
             "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for latency in (2, 20):
        for n, k in CASES:
            a, b = [next(r for r in records if (r["memory_latency"],r["lanes"],r["N"],r["K"]) == (latency,l,n,k)) for l in (16,32)]
            lines.append(f"| {latency} | {n} | {k} | {a['cycles']} | {b['cycles']} | {a['cycles']/b['cycles']:.3f} | {a['useful_mac_per_cycle']:.3f} | {b['useful_mac_per_cycle']:.3f} |")
    lines += ["", "Simulation only: no FPGA Fmax, resources, DDR GB/s, model token/s or real-model accuracy claims.",
              "input_wait counts cycles without core input valid (including startup/drain); it is not DDR stall time.",
              "input_beats + input_wait + input_blocked = measured cycles; output_wait is overlapping, not additive."]
    (OUT / "comparison.md").write_text("\n".join(lines)+"\n")


if __name__ == "__main__":
    main()
