"""An intentionally corrupt Golden must fail and leave real Verilator VCD evidence."""
import contextlib
import io
import json
from pathlib import Path
from sim_runner import run_simulation

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / "build/probes"
folder.mkdir(parents=True, exist_ok=True)
tokens = (ROOT / "build/b_fixtures/case_n1_k128.txt").read_text().split()
tokens[-1] = str(int(tokens[-1]) + 1)
fixture = folder / "intentionally_bad_golden.txt"
fixture.write_text(" ".join(tokens) + "\n")
try:
    with contextlib.redirect_stdout(io.StringIO()):
        run_simulation([ROOT / "build/core_32/Vgemv_core", "--case", fixture],
                       cwd=ROOT, label="expected-golden-failure", failure_root=folder)
except RuntimeError:
    evidence = folder / "expected-golden-failure"
    report = json.loads((evidence / "reproduce.json").read_text())
    assert report["original_returncode"] == 1 and report["replay_returncode"] == 1
    assert "B golden disagrees with decoded inputs" in (evidence / "original.log").read_text()
    trace = Path(report["trace_file"])
    assert report["trace_created"] and "$enddefinitions" in trace.read_text()
    print("PASS FAILURE_REPLAY real_verilator=PASS corrupted_golden_rejected=PASS vcd=PASS")
else:
    raise RuntimeError("Corrupt Golden unexpectedly passed")
