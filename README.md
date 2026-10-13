# LLM Accelerator — Task B Day 1–6

This repository contains the Task B implementation for the W4A8 GEMV
accelerator: the frozen A/B stream contract, signed INT4/INT8 Golden model,
reproducible handoff vectors, abstract memory model, weight reader, activation
cache, and the paired input-stream adapter used at the Task A core boundary.

## Directory layout

```text
docs/                 Interface, quantization, delivery, and integration notes
model/                INT4 packing, integer Golden, vector and stream tools
rtl/memory/           SystemVerilog memory, reader, cache, and stream adapter
scripts/              Regression and deterministic vector-generation scripts
tests/                Python tests and Task A handoff vectors
```

The three requested handoff cases are in `tests/vectors/`:

- `case_n1_k128`: N=1, K=128
- `case_n3_k256`: N=3, K=256
- `case_n2_k129`: N=2, K=129, with the physical activation stream padded to 256

Each case contains `config.json`, `weight_packed.bin`,
`activation_int8.bin`, `expected_partial.npy`, and the paired
`stream_reference.json` metadata.

## Run the Python regression

```text
python scripts/run_model_tests.py
python scripts/generate_requested_vectors.py
```

The current contract uses low-nibble-first signed INT4 packing, paired
weight/activation input handshakes, fixed 128-element groups, and low-active
asynchronous reset semantics. See `docs/interface_v1.md` before connecting
Task A's `gemv_core`.
