"""Stage tracked Qwen data for isolated K128 smoke and K2048 UART tests."""
import json
from pathlib import Path
import numpy as np
from prepare_fixed_slice_mem import prepare

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "evidence/uart_board/2026-10-21/model_slice"
    prepare(source, ROOT / "build/fixed_slice_qwen_multigroup")
    cfg = json.loads((source / "config.json").read_text())
    n, k = cfg["N"], cfg["padded_K"]
    smoke = ROOT / "build/qwen_smoke_input"
    smoke.mkdir(parents=True, exist_ok=True)
    weights = np.frombuffer((source / "weight_packed.bin").read_bytes(), dtype=np.uint8).reshape(n, k // 2)
    (smoke / "weight_packed.bin").write_bytes(weights[:, :64].tobytes())
    (smoke / "activation_int8.bin").write_bytes((source / "activation_int8.bin").read_bytes()[:128])
    np.save(smoke / "expected_partial.npy", np.load(source / "expected_partial.npy", allow_pickle=False)[:, :1])
    cfg.update(K=128, padded_K=128, source="first group of tracked Qwen UART input")
    (smoke / "config.json").write_text(json.dumps(cfg))
    prepare(smoke, ROOT / "build/fixed_slice_qwen")


if __name__ == "__main__":
    main()
