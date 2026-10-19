# System control interface v1

This wrapper adds a small internal register bus around the existing W4A8
data path. It is a simulation/bring-up interface, not an AXI-Lite or Wishbone
implementation yet.

## Register map

| Offset | Name | Access | Meaning |
|---:|---|---|---|
| `0x00` | `CTRL` | W | bit 0: `START` pulse; bit 1: `CLEAR_STATUS` pulse |
| `0x04` | `STATUS` | R | bit 0 busy; bit 1 done; bit 2 error; bit 3 activation loaded; bit 4 weight reader done; bit 5 result pending |
| `0x08/0x0c` | `WEIGHT_BASE_LO/HI` | W/R | byte address of padded W4 weight image |
| `0x10/0x14` | `ACT_BASE_LO/HI` | W/R | reserved activation source byte address; phase 1 uses host preload |
| `0x18` | `N_ROWS` | W/R | logical output row count |
| `0x1c` | `K_ELEMS` | W/R | logical activation/weight length; tail is padded internally to 128 |
| `0x20` | `ERROR_CODE` | R | 1 N=0; 2 K=0; 3 cache capacity; 4 activation not loaded; 5 start while busy; 6 reader error; 7 activation length mismatch |
| `0x24` | `CYCLE_COUNT` | R | cycles spent in the running state |
| `0x28` | `RESULT_COUNT` | R | accepted partial-sum results |

The bus is single-cycle: `bus_valid` and `bus_write` identify a transfer,
`bus_ready` is high after reset, and reads are combinational. Writes use a
non-zero byte strobe and take effect on the active clock edge. `START` and
`CLEAR_STATUS` are registered command pulses, so the task controller consumes
them on the following clock edge; a host BFM should wait one cycle before
sampling the resulting status transition.

## Execution sequence

1. Write the weight image through the host preload port and load one padded
   activation vector through the host cache-load port.
2. Program `WEIGHT_BASE`, `ACT_BASE` (reserved in this phase), `N_ROWS`, and
   `K_ELEMS`.
3. Write `CTRL.START` once. The controller validates the configuration,
   starts the weight reader and activation replay, and holds the data path
   under the existing paired valid/ready handshake.
4. Keep `result_ready` asserted when the consumer can accept a partial sum.
   `DONE` becomes sticky only after the final result handshake; `READER_DONE`
   alone does not mean the task is complete.
5. Read `STATUS`, `ERROR_CODE`, `RESULT_COUNT`, and `CYCLE_COUNT`. Write
   `CTRL.CLEAR_STATUS` before retrying after an error.

## Phase-1 boundary

The activation cache is host-preloaded because the current abstract memory
protocol permits one outstanding read and the cache replays a 256-bit beat.
The next phase can add an activation DMA/128-to-256 packer and an AXI-Lite or
Wishbone adapter without changing the task register semantics.

The control top also accepts `LANES=16`. In that mode the existing 32-lane
memory/cache stream is split by `lane_adapter_32_to_16` before the GEMV core;
the register map, group count, and completion semantics are unchanged.
