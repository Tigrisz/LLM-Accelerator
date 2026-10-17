# Quantization and test-vector format v1

This is the deliberately small, deterministic W4A8 format used by the Day 1-6 prototype. It is not a claim of GPTQ/AWQ/GGUF compatibility.

## Tensor convention

`W` has shape `[N,K]` and is stored row-major. `X` has shape `[K]`. The default group size is 128 elements along K. Every output row has an independent INT4 weight scale per group. The reference activation scale is one symmetric scale per input vector.

For a group `g`, quantization is:

```text
q = round(value / scale)
q = clip(q, -8, 7)       # weight
q = clip(q, -128, 127)   # activation
```

The RTL consumes only `qW` and `qX`. Software may reconstruct an approximate floating-point output as:

```text
Y_hat[n] = sx * sum_g(sw[n,g] * partial_sum[n,g])
```

## Files in a test case

```text
config.json
weight_packed.bin
activation_int8.bin
scales.npy
expected_partial.npy
```

`config.json` contains `N`, logical `K`, physical `padded_K`, `lanes`,
`group_size`, `seed`, and `format_version`. `padded_K` is the next multiple of
the group size. `weight_packed.bin` stores each row through `padded_K`; the
activation file stores `padded_K` INT8 values, with tail elements explicitly
zero. The binary files are little-endian. `expected_partial.npy` is signed
INT32 with shape `[N, ceil(K/group_size)]` and is computed only over logical
elements.

## Model association

The tools can generate random matrices and can later consume a real linear-layer slice. A real model slice is a shape/quantization regression target; it is not full-model inference until all model operators and runtime scheduling are implemented.

