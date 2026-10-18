"""Run a simulator; preserve the original failure and attempt one traced replay."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess


def run_simulation(command, *, cwd, label, failure_root=None, timeout=60):
    cwd = Path(cwd)
    root = Path(failure_root) if failure_root else cwd / "build/failures"
    command = [str(part) for part in command]

    def execute(env=None):
        try:
            result = subprocess.run(command, cwd=cwd, env=env, text=True,
                                    capture_output=True, timeout=timeout)
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            def decode(value):
                return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
            return 124, decode(exc.stdout), decode(exc.stderr) + f"\nTIMEOUT after {timeout}s\n"
        except OSError as exc:
            return 127, "", str(exc)

    code, stdout, stderr = execute()
    print(stdout, end="", flush=True)
    if code == 0:
        return
    # A failing first run stays a failure even if replay succeeds.
    safe_label = "".join(c if c.isalnum() or c in "-_." else "_" for c in label)
    folder = root / safe_label
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "original.log").write_text(stdout + stderr, encoding="utf-8")
    trace = (folder / "replay.vcd").resolve()
    env = os.environ.copy()
    env["TRACE_FILE"] = str(trace)
    replay_code, replay_stdout, replay_stderr = execute(env)
    (folder / "replay.log").write_text(replay_stdout + replay_stderr, encoding="utf-8")
    report = dict(label=label, command=command, cwd=str(cwd.resolve()),
                  original_returncode=code, replay_returncode=replay_code,
                  timeout_seconds=timeout, trace_file=str(trace),
                  trace_created=trace.exists() and trace.stat().st_size > 0)
    (folder / "reproduce.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    raise RuntimeError(f"{label}: simulator failed ({code}); evidence: {folder}")
