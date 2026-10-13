# W4A8 GEMV accelerator interface v1

This document freezes the Day 1 contract between task A (the compute core) and task B (model, memory, and control). The contract is intentionally independent of AXI, DDR PHY, and the eventual RISC-V bus.

## 1. Mathematical contract

The accelerator evaluates a row-major matrix-vector product:

`Y[N] = W[N,K] * X[K]`

For the first version:

- `W` is signed two's-complement INT4 in `[-8, 7]`.
- `X` is signed two's-complement INT8 in `[-128, 127]`.
- `LANES` products are consumed per accepted beat. The default is `LANES=32`.
- `GROUP_SIZE` is `128` elements. The final group is zero padded when `K` is not a multiple of 128.
- Every `{row_id, group_id}` produces exactly one signed INT32 `partial_sum`.
- Scales and bias stay in the software reference path in v1. They are not part of the bit-exact RTL result.

For row `n` and group `g`:

`P[n,g] = sum(qW[n,k] * qX[k])` for the valid elements in group `g`.

The result order is row-major: `row 0, group 0..G-1`, then `row 1`, and so on.

## 2. INT4 packing

Weights are packed in logical order `W[n,0], W[n,1], ...`.

- The low nibble of each byte is the even-indexed weight.
- The high nibble is the odd-indexed weight.
- `0xF` decodes to `-1`; `0x8` decodes to `-8`.
- A weight beat contains `LANES` consecutive INT4 values. At the default
  `LANES=32`, it is 128 bits; at `LANES=16`, it is 64 bits.
- Bit slice `[3:0]` is element 0 and bit slice `[LANES*4-1:LANES*4-4]` is
  element `LANES-1`.
- A 128-element group occupies four beats at `LANES=32` or eight beats at
  `LANES=16`; the packed group image is always 64 bytes.

Activations are sent as a `LANES*8`-bit beat containing `LANES` consecutive
signed INT8 values. The first byte is in bits `[7:0]`.

For lane `i` (where `0 <= i < LANES`) the exact bit mapping is:

`weight_data[4*i +: 4]` -> `W[n, group*128 + beat*LANES + i]`

`activation_data[8*i +: 8]` -> `X[group*128 + beat*LANES + i]`

Thus lane 0 is the low nibble/low byte and lane `LANES-1` is the most
significant nibble/byte of the beat. The activation vector is reused for every
output row; the same activation beat must be paired with the weight beat for
that row/group/beat.

## 3. Compute stream contract

The stream between task B's data path and task A's `gemv_core` is:

```systemverilog
input  logic                   clk;
input  logic                   rst_n;
input  logic                   in_valid;
output logic                   in_ready;
input  logic [LANES*4-1:0]     weight_data;
input  logic [LANES*8-1:0]     activation_data;
input  logic                   group_first;
input  logic                   group_last;
input  logic [15:0]            row_id;
input  logic [15:0]            group_id;

output logic                   out_valid;
input  logic                   out_ready;
output logic signed [31:0]     partial_sum;
output logic [15:0]            out_row_id;
output logic [15:0]            out_group_id;
```

The default widths are `LANES=32`, giving 128-bit weights and 256-bit activations. All payload and metadata fields are stable while `valid=1` and `ready=0`. A beat is consumed only on `valid && ready`. `group_first` and `group_last` apply to the accepted beat only.

Task B may produce weight and activation on independent upstream streams, but
the core boundary is one paired stream. `rtl/memory/paired_input_stream.sv`
forms `in_valid = weight_valid && activation_valid` and asserts each upstream
`*_ready` only when the other stream is valid and the core is ready. This makes
one `in_valid && in_ready` handshake consume exactly one weight/activation pair.
While blocked, both sources must keep their payload and metadata stable.

For a 128-element group with `LANES=32`, the four beats have:

| beat | `group_first` | `group_last` |
|---:|:---:|:---:|
| 0 | 1 | 0 |
| 1 | 0 | 0 |
| 2 | 0 | 0 |
| 3 | 0 | 1 |

## 4. Abstract memory contract

The memory model and the later DDR adapter use this protocol:

```systemverilog
output logic        rd_req_valid;
input  logic        rd_req_ready;
output logic [63:0] rd_addr;
output logic [31:0] rd_nbytes;

input  logic        rd_data_valid;
output logic        rd_data_ready;
input  logic [127:0] rd_data;
input  logic        rd_last;
input  logic        rd_error;
```

v1 permits one outstanding request. Addresses and lengths are 16-byte aligned. Data returns in increasing address order. A request with an invalid range must terminate with `rd_error=1`; it must not silently return a truncated transfer.

## 5. Weight reader contract

`weight_reader` accepts:

- `start`: begin a new matrix traversal;
- `weight_base`: byte address of `W[0,0]`;
- `n_rows`: `N`;
- `k_elems`: `K`;
- abstract memory response beats.

It emits the compute stream with one group at a time. The reader emits four beats per group when `GROUP_SIZE=128` and `LANES=32`. For a short final group, unused nibbles are zero and `group_last` marks the final beat.

## 6. Activation cache contract

The v1 activation cache is a reusable vector source, not a DDR master. A loader writes packed INT8 beats once. A consumer requests beats for each output row; `rewind` starts the same vector again. This makes activation reuse explicit and prevents a later DDR integration from rereading `X` for every row.

The loader pulses `load_start` before the first data beat. `load_valid_elems` is the valid element count in the current beat; all remaining bytes in a tail beat are zero. A consumer pulses `read_start` once per output row and then uses the same `valid/ready` rule as the compute stream.

The handoff files use `config.json:K` for the logical length and
`config.json:padded_K` for the physical cache stream length. The latter is the
next multiple of 128, so a tail group is present as four complete 32-lane
beats (with zero weights/activations where required).

The cache loader still sends every physical beat through `load_valid/load_ready`.
`load_valid_elems` reports logical validity for accounting (for `K=129,
LANES=32`: `32,32,32,32,1,0,0,0`), while the zero-padded bytes are written to
the cache and replayed normally.

## 7. Control conventions reserved for later days

The control block will expose the following offsets. The exact bus wrapper is intentionally deferred:

| offset | register | meaning |
|---:|---|---|
| `0x00` | `CTRL` | bit 0 `start` |
| `0x04` | `STATUS` | bit 0 `busy`, bit 1 sticky `done`, bit 2 sticky `error` |
| `0x08` | `WEIGHT_ADDR_LO` | weight byte address low 32 bits |
| `0x0c` | `WEIGHT_ADDR_HI` | weight byte address high 32 bits |
| `0x10` | `ACT_ADDR_LO` | activation byte address low 32 bits |
| `0x14` | `ACT_ADDR_HI` | activation byte address high 32 bits |
| `0x18` | `N` | output row count |
| `0x1c` | `K` | input element count |
| `0x20` | `ERROR_CODE` | first error code |
| `0x24` | `CYCLE_COUNT` | task cycle count |

## 8. Verification obligations

Task A must verify the compute core against `model/golden_gemv.py` for random, signed-boundary, tail-group, input-stall, and output-backpressure cases. Task B must provide the packed streams, metadata, and expected `{row_id, group_id, partial_sum}` sequence. No module may assume that `valid` remains asserted without checking `ready`.

Reset is low-active asynchronous. Assertion of `rst_n=0` cancels any unfinished
reader/cache load, paired input transfer, core accumulation, or pending output;
all `valid` signals and pending result state must be cleared. After reset is
released, the controller must issue a fresh load/start sequence; no pre-reset
group may resume.

