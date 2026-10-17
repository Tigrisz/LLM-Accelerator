"""Validate B artifacts, export a simple simulator fixture, run RTL against B Golden."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.golden_gemv import gemv_partial_sums
from model.gen_vectors import generate_case
from model.pack_weights import unpack_weight_matrix
from model.stream_reference import iter_gemv_beats


def export_case(folder: Path, dest: Path) -> Path:
    cfg = json.loads((folder / "config.json").read_text())
    n, k = cfg["N"], cfg["K"]
    padded = (k + 127) // 128 * 128
    assert cfg["format_version"] == 1 and cfg["group_size"] == 128
    assert cfg["padded_K"] == padded
    weights = (folder / "weight_packed.bin").read_bytes()
    activation = (folder / "activation_int8.bin").read_bytes()
    assert len(weights) == n * padded // 2 and len(activation) == padded
    assert not any(activation[k:]), "nonzero padded activation"
    decoded = unpack_weight_matrix(weights, n, k, 128)
    all_weights = unpack_weight_matrix(weights, n, padded, 128)
    assert all(not any(row[k:]) for row in all_weights), "nonzero padded weight"
    x = np.frombuffer(activation, dtype=np.int8)[:k].astype(int).tolist()
    expected = np.load(folder / "expected_partial.npy", allow_pickle=False)
    assert expected.dtype.kind == "i" and expected.dtype.itemsize == 4
    assert expected.shape == (n, padded // 128)
    np.testing.assert_array_equal(expected, gemv_partial_sums(decoded, x))
    if (folder / "stream_reference.json").exists():
        supplied = json.loads((folder / "stream_reference.json").read_text())
        assert supplied == list(iter_gemv_beats(decoded, x, cfg["lanes"], 128)), "stream metadata mismatch"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"{n} {k} {padded}\n" + " ".join(map(str, weights)) + "\n"
                    + " ".join(map(str, activation)) + "\n"
                    + " ".join(map(str, expected.flat)) + "\n")
    return dest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--integration", action="store_true")
    parser.add_argument("--random-cases", type=int, default=100)
    args = parser.parse_args()
    inputs = sorted((ROOT / "tests/vectors").glob("*/config.json"))
    cases = [p.parent for p in inputs]
    generated = ROOT / "build/b_vectors"
    for seed in range(args.random_cases):
        folder = generated / f"seed_{seed:03d}"
        generate_case(folder, 1+seed%4, [1,32,127,128,129,255,256,384][seed%8], seed=seed)
        cases.append(folder)
    for k in (2048, 6144, 8192):
        folder = generated / f"long_k{k}"
        generate_case(folder, 2, k, seed=k)
        cases.append(folder)
    for folder in cases:
        fixture = export_case(folder, ROOT / "build/b_fixtures" / (folder.name + ".txt"))
        binaries = [ROOT / "build/integration/Vtb_b_integration"] if args.integration else [
            ROOT / f"build/core_{lanes}/Vgemv_core" for lanes in (16,32)]
        for binary in binaries:
            command = [str(binary), str(fixture)] if args.integration else [str(binary), "--case", str(fixture)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
            print(f"CASE {folder.name}\n{result.stdout}", end="")
            if result.returncode:
                print(result.stderr, file=sys.stderr)
                raise SystemExit(result.returncode)
    if args.integration:
        binary = str(ROOT / "build/integration/Vtb_b_integration")
        for extra in (["--capacity"], ["--errors"], [str(ROOT / "build/b_fixtures/case_n3_k256.txt"), "--reset"]):
            subprocess.run([binary, *extra], cwd=ROOT, check=True, timeout=60)
    print(f"PASS B_ARTIFACTS cases={len(cases)} mode={'integration' if args.integration else 'core16+32'}")


if __name__ == "__main__":
    main()
