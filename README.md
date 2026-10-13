# LLM Accelerator —— 任务 B 第 1～6 天

本仓库包含 W4A8 GEMV 加速器的任务 B 实现，主要内容包括：已经冻结的
A/B 数据流接口协议、带符号 INT4/INT8 Golden 整数参考模型、可重复生成的
联调向量、抽象存储器模型、权重读取器、激活缓存，以及连接任务 A 核心的
权重/激活配对输入流适配器。

## 目录结构

```text
docs/                 接口、量化格式、交付说明和联调说明
model/                INT4 打包、整数 Golden 模型、向量和数据流工具
rtl/memory/           SystemVerilog 存储器、读取器、缓存和数据流适配器
scripts/              回归测试和确定性向量生成脚本
tests/                Python 测试以及提供给任务 A 的联调向量
```

三个指定的任务 A 联调用例位于 `tests/vectors/`：

- `case_n1_k128`：N=1，K=128
- `case_n3_k256`：N=3，K=256
- `case_n2_k129`：N=2，K=129，物理激活数据流补齐到 256

每个用例目录都包含 `config.json`、`weight_packed.bin`、
`activation_int8.bin`、`expected_partial.npy`，以及配套的
`stream_reference.json` 数据流元数据。

## 运行 Python 回归测试

```text
python scripts/run_model_tests.py
python scripts/generate_requested_vectors.py
```

当前接口协议采用低 nibble 在前的带符号 INT4 打包方式，权重和激活使用
配对输入握手，分组大小固定为 128 个元素，并采用低有效异步复位语义。
在连接任务 A 的 `gemv_core` 之前，请先阅读 `docs/interface_v1.md`。
