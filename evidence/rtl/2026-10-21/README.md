# RTL验证报告快照

summary.json和uart_full_regression.log为此前已完成17阶段回归报告的副本，
不是本次整理重新运行完整回归。board_mem.json在整理时重新针对当前PDS三个.mem
执行独立整数校验后归档，因为原build报告已被N3/K256单元测试夹具覆盖。
原build目录保留且继续被Git忽略。本次整理不修改RTL、不冒充新仿真运行。
board_mem.json是从PDS .mem独立解包并重算整数部分和的报告；其中无原模型
config时推断出的K是物理长度，模型有效列1536须结合实板归档中的model_slice/config.json。

SHA256SUMS.txt覆盖本目录除清单自身之外的全部文件。实板原始采集另见
`evidence/uart_board/2026-10-21/`，不要将仿真日志当作板端采集。
