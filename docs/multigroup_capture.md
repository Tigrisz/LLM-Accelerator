# 多组 RTL 结果导出与 B 交接

本流程依赖 PR #5 的 v1 比对工具，复用已有生成器、输入校验、存储链路及
16/32 路集成 testbench；不新增计算核心，不改固定 K=128 板端工程。
16 路使用 A 的 `paired_lane_adapter`，结果不能代替 B 板端路径验证。

## 重现

在仓库根目录、具备 Verilator 和 NumPy 的 Linux/WSL 环境执行：

```bash
make build-integration build-integration16
python scripts/check_multigroup_capture.py
```

本机 Python 应使用 `/home/tigris/projects/llm-fpga-accelerator/.venv310/bin/python`。
完整 `scripts/run_regression.py` 已加入 `multigroup-capture` 阶段；
CI 现有 `build/reports/` 上传规则会携带全部交接数据。

## 覆盖与证据

每个用例 N=3，K 为 129、255、256、257、383、384、385，分别运行 16/32 路：

| K | 每行 group 数 | padded_K | 每行补零数 | 每次输出数 |
|---|---:|---:|---:|---:|
| 129 | 2 | 256 | 127 | 6 |
| 255 | 2 | 256 | 1 | 6 |
| 256 | 2 | 256 | 0 | 6 |
| 257 | 3 | 384 | 127 | 9 |
| 383 | 3 | 384 | 1 | 9 |
| 384 | 3 | 384 | 0 | 9 |
| 385 | 4 | 512 | 127 | 12 |

输入是确定性合成数据，seed=K，权重 signed INT4、激活 signed INT8，
每组 128，权重低 nibble 在前。复用 `export_case` 检查打包数据、尾部零、
流描述与独立重算 golden。已有长 K 运算覆盖继续由原回归负责。

`--capture output.json` 只运行一次 seed=43 的随机输出背压测试，
并将最后一条结果阻塞 20 拍。记录发生在上升沿前的输出握手处：
`row_id/group_id/partial_sum` 均直接取 DUT 信号，不由 golden 或输出下标生成。
完成计数、传输计数与 idle 检查通过后才写入 `completed=true` 并结束 JSON。
若仿真中断，进程失败；文件可能是不完整 JSON，不能当作成功采集使用。

每个成功采集再派生 7 份 `source=synthetic` 故障文件：数值修改、缺失、
重复、乱序、越界 group 标签、未完成、非法数值格式。用真实 CLI 检查
退出码 1/2 及对应错误类别。故障文件不是新的 RTL 故障运行。

## 交给 B 的资料

输出根目录：`build/reports/multigroup/`。

- `summary.json`：14 个正向用例、98 个错误检测的状态，以及输入、采集和仿真器哈希。
- `lanes{16或32}_n3_k{K}/config.json`：N/K/padded_K、组长、lane 数、seed。
- `weight_packed.bin`、`activation_int8.bin`：补零后的可复用输入。
- `expected_partial.npy`：形状 `[3, ceil(K/128)]` 的 signed INT32 golden。
- `fixture.txt`、`stream_reference.json`：现有仿真接口及流参考。
- `capture.json`、`comparison.json`：实际 RTL 输出及统一比对结果。
- `fault_*.json`、`fault_*_report.json`：故障样例及拒绝证据。
- 完整回归另有 `build/reports/environment.json`：源码哈希及工具环境。

B 选定同一输入后，每次采集必须按 row-major、group-minor 导出
`3 * ceil(K/128)` 条记录；不可只导出每行最后一组，也不可先把各组整数值相加。
例如 K=384 的标签顺序为 `(0,0),(0,1),(0,2),(1,0),...,(2,2)`。
真实采集使用 `source=board` 和独立 run_id，再执行：

```bash
python scripts/compare_results.py \
  --golden build/reports/multigroup/lanes16_n3_k384/expected_partial.npy \
  --capture board_capture.json \
  --report build/reports/board_multigroup_comparison.json
```

这批报告只证明离线整数链路和结果检查流程，不证明多组已上板、DDR 链路、
真实 Qwen 切片或完整模型推理。生成器的 `scales.npy` 全为 1，仅是合成占位数据。
真实模型反量化需明确每组 scale 及其定义；不能跨不同 scale 直接累加整数部分和。
