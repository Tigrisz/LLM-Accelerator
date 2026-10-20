"""Independently check the committed 16x128 board image and stage it for RTL tests."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fpgatest/qwen_slice/prj/mem"


def read_words(name, width, count):
    lines = (SOURCE / name).read_text().splitlines()
    if len(lines) != count or any(len(line.strip()) != width // 4 for line in lines):
        raise ValueError(f"{name}: unexpected word count/width")
    return [int(line, 16) for line in lines]


def signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits-1)) else value


def main():
    weights = read_words("weights.mem", 128, 64)
    activations = read_words("activation.mem", 256, 4)
    expected = [signed(x, 32) for x in read_words("expected.mem", 32, 16)]
    x = [signed((word >> (8*i)) & 255, 8) for word in activations for i in range(32)]
    w = [signed((word >> (4*i)) & 15, 4) for word in weights for i in range(32)]
    calculated = [sum(w[row*128+k]*x[k] for k in range(128)) for row in range(16)]
    if calculated != expected:
        raise ValueError(f"Board golden mismatch: calculated={calculated}, expected={expected}")
    target = ROOT / "build/fixed_slice_qwen"
    target.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in ("weights.mem", "activation.mem", "expected.mem"):
        hashes[name] = hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
        shutil.copyfile(SOURCE/name, target/name)
    report = ROOT / "build/reports/board_mem.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(dict(source=str(SOURCE.relative_to(ROOT)), sha256=hashes,
                                     expected=expected, calculated=calculated), indent=2))
    print("PASS BOARD_MEM rows=16 K=128 independent_integer_golden=matched")


if __name__ == "__main__":
    main()
