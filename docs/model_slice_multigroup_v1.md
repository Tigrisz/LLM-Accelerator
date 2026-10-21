# Qwen2.5 多组固定切片 v1

## 当前数据边界

当前使用的 `Qwen/Qwen2.5-1.5B-Instruct` 在 layer 0 的
`self_attn.o_proj` 权重形状为 `[1536, 1536]`。为了验证固定 runner 的
`N=16、K=2048、group_size=128` 多组数据通路，本版本生成一个 2048 列的
物理 tile：前 1536 列来自真实模型，后 512 列显式补零。

`config.json` 记录：

```text
N                  = 16
K                  = 2048
padded_K           = 2048
group_size         = 128
source_cols        = 1536
zero_padded_cols   = 512
groups             = 16
```

这份数据用于验证多组流、group 标签、256 个 partial sum 和板端 ROM 布局，不能作为
“2048 个非零真实模型列”的结果。若最终需要全真实 2048 列，应改选输入维度至少为
2048 的模型层或模型。

## 生成与校验

在 WSL 的 `.venv-qwen` 环境中执行：

```bash
python scripts/extract_qwen_slice.py \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --output build/model_slices/qwen_o_proj_l0_k2048 \
  --rows 16 \
  --cols 2048 \
  --allow-zero-pad-cols

python scripts/prepare_fixed_slice_mem.py \
  build/model_slices/qwen_o_proj_l0_k2048 \
  build/fixed_slice_qwen_multigroup

python scripts/verify_board_mem.py \
  --source build/fixed_slice_qwen_multigroup \
  --target build/fixed_slice_qwen_multigroup
```

生成物应为：

```text
weights.mem       1024 lines (16 rows × 64 input beats)
activation.mem      64 lines (2048 INT8 elements / 32)
expected.mem       256 lines (16 rows × 16 groups)
stream_reference  1024 input beats before the 32-to-16 adapter
```

## RTL 验证

```bash
make lint-fixed-slice-qwen-multigroup PYTHON=.venv-qwen/bin/python
make test-fixed-slice-qwen-multigroup PYTHON=.venv-qwen/bin/python
```

`test_fixed_slice_qwen_multigroup.cpp` 要求 `result_count=256`，并检查所有 group
partial sum。现有 `make test-fixed-slice-qwen` 的 `N=16、K=128` 回归必须继续通过。
