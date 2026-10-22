# 任务B：A交接的两套多组用例转换与UART仿真

## 结论与边界

两套小用例已完成数据转换和真实RTL UART波形仿真，修复审查问题后的完整18阶段回归通过。
Python阶段55项测试通过，新增转换/报告保护测试13项。
本轮全部新采集均为`source=simulation`、`board_verified=false`，不是板端采集。
未修改现有PDS工程、约束、生产RTL或Qwen基线位流，未执行commit/push。

工作分支：`codex/b-multigroup-uart-cases`。
基准提交：`6c880d952ef7f54d01c94448dc0e4e1612258ced`；本次实现仍在未提交工作区，
不是该提交已包含本次实现。回归environment中的源码SHA256用于绑定实际测试内容。
原有`docs/task_a_uart_branch_reply_2026-10-21.md`保持原样。

## 输入及数据转换

原包：[multigroup_handoff_7fbd0b3.zip](../deliveries/incoming/multigroup_handoff_7fbd0b3.zip)。
SHA256：`6b8a17b5c3d044ba2aed992885385cb6dc9d2cd229289f2640fb643bc514dbc6`。
`7fbd0b3`只是上游包名中的提交提示，本轮未核验完整上游提交号。

原始选定文件在`tests/fixtures/a_multigroup/<case>/`，共16份，逐字节匹配ZIP原件。
[来源清单](../tests/fixtures/a_multigroup/source_manifest.json)记录ZIP成员、文件哈希及
上游summary是否提供对应哈希。原包`capture.json`属于A的离线RTL仿真，不能作为板端证据。

这两套输入是A的确定性合成整数测试（seed=K），**不是Qwen2.5模型权重切片**；
原始`scales.npy`为占位尺度，不用于本轮反量化或模型精度评估。

转换先独立重算INT4×INT8整数部分和，检查原16路stream、全部标签、A capture、
golden及长度/补零/类型，再生成B链路需要的ROM。权重低nibble优先，输出signed INT32。
原config保持`lanes=16`；生成config区分`source_lanes=16`、`rom_pack_lanes=32`和
`compute_lanes=16`。这里只改变存储打包宽度，仍使用B的32转16适配器和现有计算/UART链路，
没有用A适配器的已通过结果代替B链路仿真。

每套生成`weights.mem`（128bit）、`activation.mem`（256bit）、`expected.mem`（32bit）、
`config.json`和带输入/输出哈希的`manifest.json`。不同内容的已有输出会被拒绝覆盖。

## 验证结果

| 用例 | N/K | 组数/行 | 捕获深度 | 记录/帧字节 | 结果 |
| --- | --- | --- | --- | --- | --- |
| lanes16_n3_k256 | 3/256 | 2 | 6 | 6 / 57 | 全部标签/部分和一致，PASS |
| lanes16_n3_k384 | 3/384 | 3 | 9 | 9 / 81 | 全部标签/部分和一致，PASS |
| K256负向溢出 | 3/256 | 2 | 5 | 5 / 49 | 保留正确前缀，FAIL灯置位，测试通过 |
| K384负向溢出 | 3/384 | 3 | 8 | 8 / 73 | 保留正确前缀，FAIL灯置位，测试通过 |

每种配置均完成三次复位重跑（帧逐字节相同），及发送到第12字节时复位后的完整恢复。
测试只采样UART TX引脚，按8N1、234时钟/bit解码，不读取发送器内部状态生成capture。
正常用例检查busy→done、PASS置位/FAIL不置位、无重复帧；负向用例检查溢出不覆盖旧记录。
Python对采样bin再次解码，逐项匹配原`expected_partial.npy`，并将正常结果与A原capture对比。

正常结果按row优先、group次序输出：

```text
K256: (0,0,-1284), (0,1,-920), (1,0,-3432), (1,1,724), (2,0,-851), (2,1,2890)
K384: (0,0,-6908), (0,1,1686), (0,2,-1175), (1,0,-1560), (1,1,-1043),
      (1,2,-3218), (2,0,-4489), (2,1,215), (2,2,1156)
```

独立审查发现的旧pass报告残留和深度路径冲突均已修复；增加失败、超时、坏帧及路径隔离测试，
先观察4项失败再修复为通过。每次总测试先发布running，异常时发布failed，只有全部成功才发布pass。
历史attempt保留，禁止把历史pass解释为最新运行结果；没有未处理的审查项。

## 复现命令（WSL）

需要现有WSL Python/numpy、make、Verilator和g++，从项目根目录执行：

```bash
cd /mnt/d/GPT/qiansai_FPGA
python3 -m unittest tests.test_capture_case tests.test_multigroup_report -v
make prepare-a-multigroup PYTHON=python3
make lint-a-multigroup-uart test-a-multigroup-uart PYTHON=python3
python3 scripts/run_regression.py --base-revision 6c880d952ef7f54d01c94448dc0e4e1612258ced
```

生成ROM在`build/a_multigroup/<case>/`。
最新总测试索引：`build/reports/a_multigroup/summary.json`；确认`status=pass`后再读取其
`attempt_id`和`simulation_log`指向的`runs/<attempt_id>/<case>/complete|overflow/`。
其中`sim_run1..3.bin`是本轮RTL采样原始字节，`.json`是解码结果，
正常用例另提供`_a_format.json`供A按原格式比较。
独立直接运行默认按`depth<深度>`分目录；只有总测试入口会更新总summary。

已冻结证据在[evidence/a_multigroup/2026-10-21](../evidence/a_multigroup/2026-10-21/)：
`rom/<case>/`、`simulation/`、`regression/`及`evidence_manifest.json`。
冻结的summary保留当时build相对日志路径，复制位置见manifest内映射；不要将其当作未来运行的最新结果。

## 下一阶段：PDS与实板（尚未执行）

1. 在独立小用例工程中复用已验收UART板级接口和约束，保留Qwen基线工程及位流。
2. 先接入K256，设置N=3/K=256/CAPTURE_DEPTH=6和对应三份.mem，确认综合读取的是本套数据。
3. 完成Compile、Synthesize、Device Map、Place & Route、时序检查、Generate Bitstream，
   记录时钟、I/O、资源、警告及位流SHA256；不能用仿真通过代替这些检查。
4. 下载K256位流，重新枚举实际串口，115200/8N1打开接收后由用户按KEY0，采集三次。
   预期每次6条/57字节，与golden逐项比较row_id/group_id/partial_sum，记录LED和复位情况。
5. 对K384按N=3/K=384/CAPTURE_DEPTH=9重复流程，预期9条/81字节。
6. 分别打包两套实板原始bin、JSON、报告、约束/工程及对应位流给A独立核验；
   实板文件才能标记board来源，本轮simulation文件保留作参考，不能混入板端采集。

本轮不做逐组反量化、浮点合并或模型精度结论；整数部分和也不能无视组尺度直接合并。
