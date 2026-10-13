# Task B Day 1-6 delivery

## Scope completed

This delivery covers the B side of the first six days in the project plan. It freezes the contract and supplies independent model, memory, and control-side building blocks. It does not include task A's `gemv_core`, the Day 7 top-level integration, the Day 8 MMIO controller, or a real DDR3 adapter.

## Mapping to the plan

| Day | Planned B work | Delivered files | Purpose |
|---:|---|---|---|
| 1 | Freeze interface and create smoke framework | `docs/interface_v1.md`, `docs/quant_format_v1.md`, `docs/integration_notes.md`, `Makefile`, `scripts/run_model_tests.py` | Fix the math, packing, stream handshake, abstract memory protocol, register reservation, and task A boundary before code diverges. |
| 2 | INT4 packing/unpacking and integer Golden | `model/pack_weights.py`, `model/golden_gemv.py` | Produce bit-exact signed INT4/INT8 values and per-group INT32 partial sums. |
| 3 | Generate reproducible vectors | `model/gen_vectors.py`, `model/stream_reference.py`, `scripts/generate_requested_vectors.py` | Generate weights, activations, expected results, and the exact row/group/beat stream for task A. |
| 4 | Row-major image and test data loading | `tests/vectors/case_001/`, `tests/vectors/case_n1_k128/`, `tests/vectors/case_n3_k256/`, `tests/vectors/case_n2_k129/`, `docs/requested_vectors.md` | Provide canonical and requested cases with padded weight images, physical activation bytes, expected partials, and stream metadata. |
| 5 | Abstract memory delay/beat model | `rtl/memory/memory_model.sv` | Model one outstanding 128-bit read with latency, aligned requests, optional deterministic backpressure, host writes, and error termination. |
| 6 | Weight reader, activation cache, and paired stream adapter | `rtl/memory/weight_reader.sv`, `rtl/memory/activation_cache.sv`, `rtl/memory/paired_input_stream.sv` | Traverse row/group weight ranges, replay one loaded activation vector per output row, and consume weight/activation only as one atomic core-input handshake. |

## Verification already run

Use the bundled Python runtime or any Python 3 with NumPy:

```powershell
python scripts/run_model_tests.py
python scripts/generate_smoke_case.py
```

The regression covers signed nibble boundaries, row padding, tail groups, exact partial sums, deterministic vector generation, stream metadata, and contract/module presence. The generated case is under `tests/vectors/case_001/`.

The current Windows shell does not have a usable Verilator, Icarus, or
ModelSim executable (the vendor `vlog` installation also fails to start due to
a Windows DLL relocation error). The SystemVerilog is therefore delivered as
synthesizable-style RTL plus a checked contract. Task A's progress note reports
that its WSL Ubuntu-SRTP environment has Verilator 4.038; run the RTL tests in
that environment when the integration testbench is connected. Suggested
commands are:

```text
verilator --binary --timing --trace -Wall --top-module tb_memory_model rtl/memory/memory_model.sv tests/tb_memory_model.sv
iverilog -g2012 -Wall -s tb_memory_model -o build/tb_memory_model.vvp rtl/memory/memory_model.sv tests/tb_memory_model.sv
```

The first HDL tests should check memory byte writes and aligned/error reads, reader address/metadata progression across rows and groups, and activation-cache replay with output stalls. These require task A's final stream port names only at the integration boundary; the v1 protocol is already frozen.

## Task A handoff

Task A must implement `gemv_core` against `docs/interface_v1.md`. For the canonical case, connect:

```text
weight_reader.weight_*      -> paired_input_stream weight fields
activation_cache.read_*     -> paired_input_stream activation fields
paired_input_stream.*       -> gemv_core input fields
gemv_core output            -> comparison against expected_partial.npy
```

The activation cache must be rewound for each output row. The reader emits four 128-bit weight beats per 128-element group at the default 32-lane setting. Any rename or split of the stream fields should be handled by a small adapter and recorded as an interface revision.

The reset contract is low-active asynchronous: reset cancels the reader, cache,
adapter-side transfer, core accumulation, and pending result. After release,
the controller restarts from a fresh load/start sequence.

