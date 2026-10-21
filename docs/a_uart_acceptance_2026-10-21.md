# A：UART 交付验收与反量化一致性

## 已验收范围

B 的 UART 源码、约束、工程与采集证据已提交至 `c548e80`，此前交接文档中的
“尚未提交”是打包时的历史状态。A 保留 B 的 RTL、PDS 配置和位流内容。
仅将 UART 顶层未使用信号改名，替代 Verilator 4.038 不认识的 lint 注释；不重新声称已综合该源码。

本次数据为 N=16、物理 K=2048、有效列1536，128元素/组、16组/行。
来源为 B 归档的3次实板UART采集，A独立离线重解码；不是A重新操作硬件。
每帧2057字节、256条记录，共768条板端记录全部标签、顺序、值匹配。
三帧完全一致，最后4组每行全零，保留全部64条补零组结果。

位流 SHA-256：`718330d02168d8a9af8ed09f5d24bc70e69eaad67431faef7639c3c7382eef16`。
原始帧 SHA-256：`410f0086fa79888f974e245f9ac878eaad452fdd9ee3adc5eb3f62f484077cf0`。
交付 ZIP SHA-256：`c63e831009f4c5ea3846df338e9de1db0f6605b425e3cfa0310aa383c9b74f8d`。

## 可重现验收

完整回归：`python scripts/run_regression.py`。新增 `uart-acceptance` 阶段同时验证
三份归档板端帧和本次仿真生成的 `build/reports/qwen_uart_sim.bin`，严格区分来源。
可独立执行 `python scripts/audit_uart_delivery.py`，无需串口或Torch。
已有仿真文件时可追加 `--simulation build/reports/qwen_uart_sim.bin`。

输出在 `build/reports/uart_acceptance/`：

- `board-run{1,2,3}.json`：从原始帧生成的统一格式，保留原始SHA-256和来源说明。
- `*_comparison.json`：统一比对工具的结果，板端记录同时核对位流哈希。
- `summary.json`：输入/尺度/采集哈希、配置、逐行反量化值及限制。
- `uart-rtl*`：可选的本次RTL仿真结果，source=simulation。

验收检查 ZIP 及26个成员、归档哈希清单、位流与初始化文件关联；
由打包INT4/INT8独立重算256个整数部分和，同时核对NPY和MEM golden。
原始UART经B解码器解析后转为统一格式，统一比对工具另行严格检查顺序、数量和标签。
completed仅表示完整帧已解析，不是UART携带的硬件done状态。

## 反量化结果的含义

计算 `sum_g(partial_sum[r,g] * scales[r,g] * activation_scale)`，使用float64。
独立路径把每个量化权重乘对应组尺度、每个量化激活乘激活尺度，再做元素级点积。
三次板端和RTL结果均与该独立路径在 `rtol=1e-12, atol=1e-12` 下吻合。
合成非均匀尺度用例额外防止“先累加所有整数组和，再乘一个尺度”的错误。

这只验证反量化使用和结果一致性，未评估相对原始模型浮点输出的量化误差。
包内缺少原始浮点权重/激活/输出，不能据此声明模型精度。
补充分支 `6c880d9` 已提供 checkpoint `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`、
提取命令及依赖版本。B报告固定snapshot重放与交付数据逐字节匹配；A核对归档和载荷哈希，
未在A环境重新加载模型。详见 [B复现说明](qwen_checkpoint_reproduction_2026-10-21.md)。
UART v1也不携带CRC、位流ID或LED状态，硬件来源、复位和LED依据B的采集记录。

## 复现修复

回归复用B的Make目标，从已提交PDS ROM准备K2048 UART输入，
从 `tests/fixtures/qwen_n16_k128` 准备历史K128 smoke输入；
不依赖旧build缓存，不改PDS板端ROM，也不保留重复的首组裁切准备逻辑。
MEM文本固定LF，避免Windows自动CRLF转换导致字节哈希不一致。
`verify_slice`将临时用例报告写入其target，只有默认板端输入/目标的CLI调用写正式`build/reports/board_mem.json`，
避免后续Python测试覆盖N16/K2048报告。

## 交给 B 的下一步

1. 本基线整数和UART交付已通过A离线验收；无须重发当前三份采集。
2. checkpoint revision、提取命令和依赖版本已收到；保留固定snapshot复现流程。
3. 提供同一切片、同一token的原始浮点权重和激活（或可信浮点参考输出），供量化误差评估。
4. 下一轮N3/K256、N3/K384使用PR6各自golden与输入，分别应有6/9条记录。
   冻结输入哈希后，B另行构建和上板采集；当前N16/K2048结果不能替代它们。

完整模型推理、DDR链路和吞吐性能另行验证，不从UART发送耗时推导token/s。
