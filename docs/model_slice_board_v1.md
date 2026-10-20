# Board-only real model slice v1

This flow separates build-time model preparation from FPGA runtime. The
development machine may run `extract_qwen_slice.py` and
`prepare_fixed_slice_mem.py`; the programmed FPGA then reads only the
generated `.mem` images and does not receive model data from a host.

## Recommended first slice

Use `Qwen2.5-1.5B-Instruct` layer 0 `self_attn.o_proj`, with a small tile:

```text
N_tile = 16 (or 1 for the smoke fixture)
K_tile = 128
LANES = 16
group_size = 128
```

`K=128` is intentional: the board runner v1 has one group and compares each
row's INT32 result on the FPGA. A later multi-group runner must add a row
accumulator and a DDR-backed scheduler.

## Offline preparation

```bash
python3 scripts/extract_qwen_slice.py \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --output build/model_slices/qwen_o_proj_l0 \
  --rows 16 --cols 128

python3 scripts/prepare_fixed_slice_mem.py \
  build/model_slices/qwen_o_proj_l0 \
  build/fixed_slice_qwen
```

The first command needs `torch`, `transformers`, and the model checkpoint only
at build time. The second command creates:

- `weights.mem`: 128-bit little-nibble-first W4 weights;
- `activation.mem`: 256-bit packed INT8 activation beats;
- `expected.mem`: board-side INT32 expected partial sums.

The repository keeps the original `N=1` smoke regression separate from the
real `N=16` Qwen regression.  After the Qwen `.mem` files exist, run:

```bash
make lint-fixed-slice-qwen
make test-fixed-slice-qwen
```

The Qwen target checks the three initialization files, instantiates the
runner with `N=16`, and expects 16 verified row results.  The original
`make test-fixed-slice` target continues to use the synthetic `N=1` fixture.

## FPGA runtime

Instantiate `fixed_slice_qwen_demo_top` in the PDS project. This wrapper
already fixes `N=16`, `K=128`, and the three Qwen initialization paths. Add the
`.mem` files as ROM/BRAM initialization files and connect `clk/rst_n` plus the
four status outputs to board pins, LEDs, UART status logic, or a board
register. If the PDS project requires different resource paths, override the
wrapper's three string parameters without changing the data protocol.
The wrapper ties `start` to reset release, so the slice runs automatically:

```text
rst_n released → fixed runner starts → FPGA GEMV16 → on-board compare
                                      → led_pass or led_fail
```

No host preload, CPU BFM, or runtime Python process is part of this path.
