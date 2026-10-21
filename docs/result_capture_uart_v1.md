# 板端结果逐项读回 v1

本版本把 `fixed_slice_runner` 的真实输出事件直接写入片上捕获 RAM，再由 UART TX 在计算完成后顺序发送。捕获路径使用 runner 输出的 `result_valid/result_row_id/result_group_id/result_partial_sum`，因此不根据结果序号推断标签。

## 数据格式

每条记录 64 bit，RAM 中的位布局为：

```text
[63:32] partial_sum  (signed INT32)
[31:16] group_id
[15:0]  row_id
```

默认 Qwen2.5-1.5B-Instruct 验证切片为 `N=16, K=2048`，共有 16×16=256 条记录，捕获深度为 256。写满后继续到来的结果不会覆盖旧记录，`capture_overflow` 置 1。

## UART 帧

UART 空闲和停止电平为 1，数据位低位先发送。帧字节为：

```text
A5 5A 01 count[7:0] count[15:8] count[23:16] count[31:24]
record[0] ... record[count-1]
5A A5
```

每条 `record` 依次发送 `row_id` 两字节、`group_id` 两字节、`partial_sum` 四字节，均为 little-endian。默认 `CLKS_PER_BIT=234` 对应约 27 MHz 时钟下的 115200 baud；实际 PDS 工程应按板卡时钟和 UART 引脚约束重新计算该参数。

## RTL 文件

- `rtl/debug/result_capture_buffer.sv`：结果捕获 RAM、计数和溢出标志。
- `rtl/debug/result_uart_tx.sv`：UART 帧和串行发送状态机。
- `rtl/debug/result_capture_uart.sv`：捕获 RAM 与 UART 的组合封装。
- `rtl/model/fixed_slice_qwen_uart_top.sv`：Qwen N=16、K=2048 的可选读回顶层。

现有 LED-only 顶层可继续保留。PDS 当前使用新增的
`fixed_slice_qwen_uart_board_top`，仅暴露时钟、复位、四 LED、UART TX 共 7 个
IO；其余计数器留在内部。UART TX 已根据硬件手册及配套 PG2L100H 工程确认
为 C24、LVCMOS33，连接板载 CP2102。原 27 MHz 时钟、复位和 LED 约束继续
使用，新增 `constraints/fixed_slice_qwen_uart_io.fdc` 补充 UART 与异步端口约束。

## 仿真入口

```text
make lint-result-capture
make test-result-capture
make lint-uart-board
make test-uart-board
make test-uart-board-overflow
```

单元测试覆盖 6 条记录的 row/group/sum 顺序、负数 partial_sum 和满深度溢出。
完整板级测试使用 `CLKS_PER_BIT=234`，从 TX 波形解码全部 256 条记录，检查
三次复位重跑、发送中复位恢复以及深度 255 时的板级 FAIL。

接收端可以把 UART 去掉起始位、数据位和停止位后的原始帧保存为二进制，再用下面的脚本导出带 `source=board` 标记的 JSON：

```text
python3 scripts/decode_result_uart.py capture.bin --source board --output capture.json
```

解码器默认 `source=unknown`，仅格式解析不证明数据来自硬件。仿真文件必须
显式标注 `--source simulation`。加入 `--expected`、`--rows`、`--groups` 可逐项
检查缺失、重复、越界标签及数值。当前 v1 帧没有 CRC 或计算状态字段，完整性
由长度/帧尾与全部黄金值比较确认；LED PASS/FAIL 单独记录。

板端操作、PDS 报告与验收状态见 `docs/uart_board_validation_2026-10-21.md`。
