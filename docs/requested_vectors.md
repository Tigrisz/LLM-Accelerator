# Task A handoff vectors

The requested deterministic cases are under `tests/vectors/`:

| directory | logical shape | physical activation length | weight file | expected file |
|---|---:|---:|---:|---:|
| `case_n1_k128` | `N=1, K=128` | 128 INT8 bytes | 64 bytes | `[1,1]` INT32 |
| `case_n3_k256` | `N=3, K=256` | 256 INT8 bytes | 384 bytes | `[3,2]` INT32 |
| `case_n2_k129` | `N=2, K=129` | 256 INT8 bytes (`padded_K`) | 256 bytes | `[2,2]` INT32 |

Each directory contains:

- `config.json`: logical `K` and physical `padded_K`;
- `weight_packed.bin`: row-major signed INT4, low nibble first, each row padded;
- `activation_int8.bin`: signed INT8, zero-padded to `padded_K`;
- `expected_partial.npy`: signed INT32 partial sums over logical elements;
- `stream_reference.json`: row/group/beat metadata and paired payload hex.

Regenerate all three cases with:

```text
python scripts/generate_requested_vectors.py
```
