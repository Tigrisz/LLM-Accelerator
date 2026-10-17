# Task B integration notes for task A

## What task B provides by Day 6

- `model/pack_weights.py`: deterministic signed INT4 pack/unpack.
- `model/golden_gemv.py`: bit-exact integer GEMV reference and metadata generation.
- `model/gen_vectors.py`: reproducible random vector cases.
- `rtl/memory/memory_model.sv`: abstract 128-bit read response with latency, beat-rate limit, and optional pseudo-random backpressure.
- `rtl/memory/weight_reader.sv`: row/group traversal and group metadata generation.
- `rtl/memory/activation_cache.sv`: packed INT8 vector loader and replay source.
- `rtl/memory/paired_input_stream.sv`: atomic pairing of the independent weight
  and activation sources at the `gemv_core` boundary.

## What task A must provide

Task A owns `gemv_core` and its exact stream timing. It must accept the fields in `docs/interface_v1.md`, hold payload stable under output backpressure, and emit one result for every accepted `{row_id, group_id}` group.

## First integration sequence

1. Use `model/gen_vectors.py` to create a small `N=3, K=256` case.
2. Load the activation beats into `activation_cache`.
3. Point `weight_reader` at the memory model and set `n_rows=3`, `k_elems=256`.
4. Connect the reader and cache to `paired_input_stream`, then connect its
   single paired output to task A's core. Replay the activation vector at each
   row boundary; one core input handshake consumes one weight/activation pair.
5. Compare the core's output tuple against `expected_partial.npy` in row/group order.

For a tail case, load all `padded_K/LANES` physical beats. Drive
`load_valid_elems` from the logical tail counts (for `K=129, LANES=32` this is
`32,32,32,32,1,0,0,0`) and assert `load_last` only on the final physical beat;
the zero-filled beats are still needed for the second 128-element group.

The boundary is settled as a paired weight/activation beat. The adapter gates
each upstream `ready` with the other stream's `valid`, so a stalled or delayed
activation cannot advance the weight reader by itself. The cache still supports
replay so the storage path does not reread activations for every row.

## Open items for Day 7

- Select the final `LANES` value after task A's core port is available.
- Decide whether task A wants `group_first/group_last` on every beat or a separate group descriptor channel.
- Add a small top-level adapter if task A uses different signal names.
- Confirm whether the later RISC-V bus is AXI-Lite, Wishbone, or another protocol before writing the bus wrapper.

