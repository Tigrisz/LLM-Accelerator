# 结果文件与比对工具 v1

## B 需要导出什么

每个文件只包含一次任务的全部结果。UART/JTAG/寄存器读取程序可在主机侧组装此 JSON；
不要求 FPGA 直接发送 JSON。当前板端只有 LED，逐行结果读回接口仍需 B 实现。

```json
{
  "format_version": 1,
  "source": "board",
  "run_id": "unique-run-id",
  "completed": true,
  "results": [
    {"row_id": 0, "group_id": 0, "partial_sum": 203},
    {"row_id": 1, "group_id": 0, "partial_sum": "0x000000d3"}
  ]
}
```

上例仅演示两行格式，不是完整板端采集结果。当前切片应有 16 行、group_id 全为 0。

- row_id/group_id 从 0 开始，按 row-major、group-minor 顺序，每对标签恰好出现一次。
- partial_sum 为有符号 INT32 十进制整数，或 `0x` 加恰好 8 位十六进制补码。
  例如 `0xffffffff` 表示 -1。十进制 4294967295 不会被静默转成 -1。
- completed 为布尔值，仅在确认任务结束且全部数据导出后设为 true。
- source 必须为 board、simulation 或 synthetic，禁止把参考值复制出来后标为 board。
- run_id 为非空字符串，用于区分任务；同一文件不要拼接多次复位运行。
- 可在顶层补充 bitstream_sha256、输入文件哈希、板卡、时钟和采集时间。
  `--bitstream` 会强制核对文件 SHA-256 与 capture 声明；只验证版本关联，不证明实际烧录动作。
- 当前工具严格检查顺序；即使数值按标签匹配，乱序也报告失败。

## 如何比对

在仓库根目录执行，板端采集文件由 B 提供：

```bash
python scripts/compare_results.py \
  --golden fpgatest/qwen_slice/prj/mem/expected.mem \
  --rows 16 --groups 1 \
  --capture board_capture.json \
  --report build/reports/board_comparison.json
```

以后多组切片可直接使用已有二维 INT32 `expected_partial.npy`：

```bash
python scripts/compare_results.py \
  --golden tests/vectors/case_n2_k129/expected_partial.npy \
  --capture board_capture.json \
  --report build/reports/board_comparison.json
```

也可追加 `--bitstream path/to/file.sbit`，此时采集文件必须携带匹配的 bitstream_sha256。
工具禁止报告覆盖输入文件。退出码：0=全部匹配，1=结果/完整性不匹配，2=格式或输入错误。
报告包括 source、run_id、数量、输入哈希、首个错误、分类计数和最多 100 条错误详情。
缺失、重复、乱序等类别可能同时出现，不应将各类别数量相加当作错误结果行数。
`status=pass` 仅表示该文件与该 golden 匹配；是否为实际板端数据取决于采集来源。

## 验证和限制

完整回归会执行 Python 异常用例，再由 Qwen RTL 仿真导出实际计算结果并交给工具比对。
生成文件为 `build/reports/qwen_simulation_capture.json`，明确标记 source=simulation。
固定切片测试封装用结果计数推导 row_id，group_id=0；runner 自身同时检查核心标签与 golden。
它不提供真实 UART/JTAG 链路验证，不能替代板端输出采集。

本工具检查量化整数部分和，不检查反量化精度、模型质量或完整推理。

多组集成链路的实际握手导出、边界用例及交接文件见
[多组 RTL 结果导出](multigroup_capture.md)。
