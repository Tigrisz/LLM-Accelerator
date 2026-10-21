# A/B 14 天计划进度与后续联调方案

日期：2026-10-20
依据：最初 14 天开发计划、当前 `main` 分支源码、测试/交接文档，以及 PDS 工程记录。

## 1. 模型基线与判断口径

最初计划中的模型已经调整。本报告统一采用当前实际使用的
`Qwen2.5-1.5B-Instruct`，不再把旧模型名称作为当前交付目标。当前板端切片的固定配置是：

```text
model       = Qwen2.5-1.5B-Instruct
layer       = 0
module      = model.layers[0].self_attn.o_proj
N           = 16
K           = 128
group_size  = 128
LANES       = 16（存储侧可保持 32 路，再由适配器拆为 16 路）
quant       = symmetric W4A8
runtime     = FPGA 复位释放后读取固化 .mem，自检并输出状态
```

`K=128` 是当前固定切片 runner 的单组验证范围，不代表已经完成整个
`Qwen2.5-1.5B-Instruct` 的 FPGA 推理。后续可以把同一层扩展到多组 `K=2048`，
但必须增加组间累加、调度和结果读回验证。

## 2. 总体结论

成员 A 已完成计算核心和主要流协议联调，达到 D9 附近的计算侧目标，并完成
16/32 路适配、随机停顿、输出反压、复位和完整抽象存储链路验证。

成员 B 已完成模型/存储/控制侧的第一版系统、Qwen2.5 固定切片、16 路板端路径、PDS
工程、约束和位流生成，达到固定切片板端 bring-up 阶段。B 的 Qwen 切片已经可以在
仿真中由三份 `.mem` 文件进行 16 行结果自检。

当前还没有完成的范围是：

- Qwen2.5 真实切片的多组 `K=2048` 调度和组间累加；
- 双缓冲、真实 DDR 适配、AXI/RISC-V 外部总线和完整模型运行时；
- 板上逐行结果读回，以及由板上观测记录证明 `led_pass/led_fail` 的真实状态；
- 完整 Transformer 推理，包括 RMSNorm、RoPE、Attention、KV Cache、Tokenizer 和采样。

因此，当前项目可以称为“Qwen2.5 真实固定切片的 W4A8 FPGA 自检路径已形成”，
不能称为“完整 Qwen2.5 模型已经在 FPGA 上运行”。

## 3. 按 14 天计划核对 A 的进度

| 计划阶段 | A 的实际完成情况 | 判定 |
|---|---|---|
| D1-D2：冻结 GEMV 接口、INT4 解释和整数参考 | 完成 `interface_v1.md` 约定；完成 INT4 解包、符号扩展和单路 MAC；与 B 的 nibble/激活顺序对齐 | 已完成 |
| D3-D4：16/32 路计算和分组累加 | 完成 `gemv_core`、`group_acc`、`row_id/group_id`、`group_first/group_last` 处理 | 已完成 |
| D5-D6：握手、停顿、反压和复位 | 覆盖输入空闲、输出阻塞、payload 保持、尾组补零、复位重启和连续任务 | 已完成 |
| D7/M2：内存到计算的首次端到端联调 | `memory_model → weight_reader/activation_cache → paired_input_stream → gemv_core` 与独立 Golden 对齐 | 已完成 |
| D8-D9：系统边界回归 | A 侧已覆盖连续数据流、错误配置、容量、复位和结果反压；系统控制器由 B 提供 | 计算侧完成，系统侧共同完成 |
| D10：真实模型切片核验 | 已支持 Qwen 固定切片的数据格式和 16 路核心路径；当前真实板端仅验证单组 `K=128` | 单组完成，多组待做 |
| D11：16/32 路性能比较 | 已有确定性抽象存储模型基准；结果只代表仿真延迟/停顿条件 | 已完成仿真基准 |
| D12：双缓冲 | 仓库中没有可验收的 ping-pong 实现 | 未完成 |
| D13-D14：收口和演示 | lint、回归和 PDS 交付路径已有记录；板端逐行结果和 LED 复位重跑证据仍需补齐 | 部分完成 |

### A 当前交付物

- `rtl/compute/int4_unpack.sv`
- `rtl/compute/mac_lane.sv`
- `rtl/compute/gemv_core.sv`
- `rtl/compute/group_acc.sv`
- `rtl/memory/paired_input_stream.sv`
- `rtl/compute/paired_lane_adapter.sv`
- `docs/interface_v1.md`、`docs/compute_interface_v1.md`
- 16/32 路核心、适配器、抽象存储链路和 Golden 对比测试

## 4. 按 14 天计划核对 B 的进度

| 计划阶段 | B 的实际完成情况 | 判定 |
|---|---|---|
| D1-D2：协议、量化格式和向量约定 | 完成 `interface_v1.md`、`quant_format_v1.md`、INT4 packing/unpacking 和分组整数 Golden | 已完成 |
| D3-D4：向量、内存镜像和抽象存储 | 完成向量生成、`memory_model`、`weight_reader`、`activation_cache` 和配对输入流 | 已完成 |
| D5-D6：存储链路和异常处理 | 完成延迟/反压、容量判断、错误响应消费、复位重启和严格 lint | 已完成 |
| D7/M2：与 A 的端到端链路 | 107 个合成向量与 16/32 路核心及 32 路完整链路通过；已合入主分支 | 已完成 |
| D8-D9：控制器和系统回归 | 完成内部寄存器总线、任务控制器、CPU BFM、16/32 路控制回归和 `done/error` 语义 | 已完成仿真交付 |
| D10：当前模型真实切片 | 完成 Qwen2.5-1.5B-Instruct layer 0 `self_attn.o_proj` 的 `N=16,K=128` 固定切片、三个 `.mem` 文件和 runner | 单组完成 |
| D11：性能和并行度实验 | 完成抽象存储条件下 16/32 路确定性比较；没有真实 DDR 带宽数据 | 仿真完成 |
| D12：双缓冲/预取 | 尚未发现可验收的双缓冲实现 | 未完成 |
| D13：PDS 工程收口 | 已有 PDS 工程、约束、综合/布局布线和位流生成记录；PDS 记录中的资源/时序属于工具结果 | 基本完成 |
| D14：板端演示 | 位流已经生成，但仍需实际板卡复位、自动运行、LED/UART/寄存器状态记录 | 待完成验收证据 |

### B 当前交付物

- `scripts/extract_qwen_slice.py`
- `scripts/prepare_fixed_slice_mem.py`
- `scripts/verify_board_mem.py`
- `rtl/memory/memory_model.sv`
- `rtl/memory/weight_reader.sv`
- `rtl/memory/activation_cache.sv`
- `rtl/control/control_regs.sv`
- `rtl/control/task_controller.sv`
- `rtl/control/accelerator_control_top.sv`
- `rtl/compute/lane_adapter_32_to_16.sv`
- `rtl/model/fixed_slice_runner.sv`
- `rtl/model/fixed_slice_qwen_demo_top.sv`
- PDS 工程、约束文件、三个 Qwen `.mem` 初始化文件和位流

## 5. 成员 B 接下来应该做什么

### B1：先完成当前单组切片的板端验收

1. 固定当前三份 `.mem` 文件、顶层源码、约束和位流的 SHA256。
2. 在盘古 100Pro+ 上下载位流，复位后确认 runner 自动启动。
3. 记录 `led_done`、`led_pass`、`led_fail` 的实际状态；至少进行一次复位后的重复运行。
4. 若板上没有逐行读回通道，增加最小 UART/JTAG/寄存器读回方案，输出 `row_id`、`group_id`、`partial_sum`、`result_count`。
5. 保存板卡型号、时钟、位流文件、`.mem` 文件哈希和运行日志。

这一步完成后，当前 `N=16,K=128` Qwen2.5 固定切片才有完整的“生成文件→综合→位流→板上计算自检”证据链。

### B2：补齐模型元数据

为当前切片保存以下信息，并和 `.mem` 一起归档：

- 模型仓库名、具体 revision/commit 和 `config.json`；
- 层名、权重原始形状、`rows/cols`、`group_size`、`padded_K`；
- W4 权重的量化规则、激活 A8 规则、每行/每组 scale；
- `weights.mem`、`activation.mem`、`expected.mem` 的 SHA256；
- Python 端重新解码后得到的 16 个 INT32 expected 值。

当前提交的 `.mem` 可以独立验算，但缺少完整 revision/config/scale 元数据，不能仅凭文件追溯 checkpoint。

### B3：把当前切片扩展到多组 K

以同一 Qwen2.5 层为目标，先做 `N=16,K=2048,G=128`：

1. 离线导出 16 行、2048 列的真实权重和 A8 激活；
2. 生成每行 16 个 group 的 W4/A8 流和 expected partial sums；
3. 在 runner 中增加组间累加器，保持 `row_id/group_id` 顺序；
4. 明确最后一组的零填充和有效 K，避免把 padding 当作有效乘加；
5. 保留现有 `K=128` smoke test，确保扩展不会破坏基本验收；
6. 先仿真通过，再把多组初始化内容固化到 BRAM/ROM，最后上板。

### B4：准备真实内存/CPU 接入的边界

在多组切片正确后，再设计 DDR/CPU 外围：

- 先定义 128-bit 存储读口到 16 路核心的请求、返回和反压时序；
- 将当前内部单周期寄存器总线包装为目标平台所需的 AXI-Lite、Wishbone 或其他总线；
- 保留已验证的 `gemv_core` 数值和配对流语义；
- 只有测到真实 DDR 的持续带宽和延迟后，才决定预取、缓存容量和双缓冲策略。

## 6. A/B 必须进行的联调

### 联调 1：数据格式和流接口

B 提供一个固定种子向量和一个 Qwen2.5 真实切片，包含：

```text
weight_data、activation_data、row_id、group_id、group_first、group_last
expected(row_id, group_id, partial_sum)
```

A 使用同一份打包数据逐拍检查。双方必须确认：

- W4 低 nibble/高 nibble 顺序；
- A8 字节顺序；
- 16 路适配器的低半拍/高半拍顺序；
- `group_first/group_last` 只对实际握手生效；
- `valid && !ready` 时所有 payload 和标签保持稳定；
- 每个 `{row_id,group_id}` 只输出一次 INT32 partial sum。

### 联调 2：多组 K 的结果语义

B 负责产生每组 partial sum 和 scale 元数据，A 负责核对核心输出。双方共同确定：

- 核心输出仍是整数 partial sum；
- 组间累加是在 runner、控制顶层还是结果收集器完成；
- 反量化只在软件/结果端进行，还是增加片上定点缩放；
- 尾组的有效元素数、零填充和最后一组标记。

验收条件是逐条比较 `(row_id, group_id, partial_sum)`，并另外比较最终行累加值；不能只比较总和。

### 联调 3：控制、完成和错误路径

B 驱动 `CTRL/STATUS` 和任务 FSM，A 检查计算侧行为。必须覆盖：

- `START` 只接受一次，busy 时重复 start 返回错误；
- `done` 只在最后一个结果完成握手后置位；
- reader 完成但结果仍阻塞时，任务不能提前结束；
- 非法 `N/K`、地址、缓存容量和复位重启有明确 error code；
- 16 路和 32 路使用相同的结果计数和完成语义。

### 联调 4：板端结果和回归

B 提供位流、`.mem`、板卡运行日志和状态读回；A 提供结果比对脚本。共同执行：

```bash
make lint-fixed-slice-qwen
make test-fixed-slice-qwen
make test-integration PYTHON=python
make test-integration16 PYTHON=python
python scripts/run_regression.py
```

回归通过只说明仿真/静态验证通过；板端结论还必须有实际 LED/UART/JTAG/寄存器观测记录。

## 7. 近期联调顺序和验收门槛

建议按以下顺序推进：

1. B 完成当前 `N=16,K=128` 板端复位运行和状态记录；A 完成结果读回/比对工具。
2. B 补齐模型 revision、config、scale 和文件哈希；A 审核数据布局和 expected 值。
3. 双方以 `N=16,K=2048` 的 Qwen2.5 多组切片做仿真联调。
4. 保留 K=128 smoke、16/32 路适配器和原有随机回归，执行完整回归。
5. 多组仿真通过后，更新 PDS 顶层/BRAM 初始化，重新综合、布局布线、生成位流并上板。
6. 最后再进入真实 DDR、CPU 总线和双缓冲设计。

每一步都要保留输入文件哈希、配置、命令、工具版本和 PASS/FAIL 结果。没有这些证据时，
只能称为代码已实现或仿真已通过，不能称为板端功能已验收。

## 8. 当前明确不应宣称的结果

- 不能把抽象存储模型的周期表当作真实 DDR 带宽或 token/s；
- 不能把 PDS 的 bitstream/configuration done bit 当作计算 pass；
- 不能把 `N=16,K=128` 单组自检当作完整 Qwen2.5 推理；
- 不能把已有 lint、仿真或综合记录当作已完成板上逐行结果读回；
- 不能在没有实际测量前声称双缓冲或 AXI/RISC-V 已完成。

## 9. 证据索引

- A 计算和联调：`docs/a_progress.md`、`docs/compute_interface_v1.md`、`docs/b_handoff_2026-10-17.md`
- B 模型/存储/控制：`docs/day1_6_delivery.md`、`docs/control_interface_v1.md`、`docs/integration_notes.md`
- 当前 Qwen2.5 板端切片：`docs/model_slice_board_v1.md`
- A/B 合并和 PDS 记录：`docs/integration_status_2026-10-20.md`
- 16/32 路适配和基准：`docs/lane16_handoff_2026-10-19.md`、`docs/lane_benchmark_2026-10-19.md`
- 回归入口：`scripts/run_regression.py`、`Makefile`

