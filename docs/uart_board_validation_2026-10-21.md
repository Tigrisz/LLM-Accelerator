# Qwen UART 板级接入与验证记录

> 提交整理后，实板证据归档在`evidence/uart_board/2026-10-21/`，
> PDS/RTL报告快照在`evidence/pds/2026-10-21/`及`evidence/rtl/2026-10-21/`，
> 任务A交付ZIP在`deliveries/`。下文build/artifacts仍表示原始运行输出位置。

日期：2026-10-21。模型：Qwen2.5-1.5B-Instruct 固定 W4A8 切片，
N=16、物理 K=2048、group_size=128，共 256 条部分和。

## 当前结论

源码、约束和 PDS 工程已完成接入，RTL 仿真和 PDS 位流生成通过。
**实际板端 UART 采集和三次KEY0复位重跑已通过**：安装CP2102驱动后识别
COM10，三次各接收2057字节、256条结果，逐项黄金值比较全部一致，三帧逐字节相同。
用户逐轮确认LED1/LED2亮、LED3灭。详细记录见
`docs/uart_board_capture_2026-10-21.md`，原始bin、JSON及校验清单位于
`artifacts/uart_board/2026-10-21/`（该目录被Git忽略，交付时须另行打包）。
`build/reports/qwen_uart_sim.bin` 为仿真输出，不能当成任务A需要的板端数据。

FPGA 复位后自行从固化 .mem 数据计算、比较及发送，电脑只接收/记录。
这仍是模型切片验证，不代表整个 Qwen 模型端到端推理。

## 工程变化

- 新物理顶层：`rtl/model/fixed_slice_qwen_uart_board_top.sv`，七个外部 IO。
- 功能顶层：`rtl/model/fixed_slice_qwen_uart_top.sv`，计算完成后发送一帧。
- `rtl/debug/`：64-bit 结果捕获 RAM、UART 编码及组合封装。
- 根目录及 PDS 的 runner 增加真实结果事件输出；旧调用方显式接入未使用线。
- 板级复位采用异步置位、两拍同步释放；KEY0 按下清空本轮状态，释放后重跑。
- 板级 PASS 同时要求计算比较通过、捕获无溢出、两个计数均为 256。
- `scripts/verify_board_mem.py` 修复无 config.json 时的多组行数推断；验证用
  staging 目录改为 `build/fixed_slice_board_verified`，避免覆盖旧 K128 fixture。

PDS 已保存的工程：`fpgatest/qwen_slice/prj/prj.pds`。UART 模块通过项目相对
路径引用根目录源码，不需要复制第二套。工程内继续使用原 PDS runner/compute
文件，避免重复定义。三个初始化文件仍为 `prj/mem/*.mem`。

## 引脚依据与配置

硬件实验指导手册第 2.1.3.2.5 节（印刷页39-40，PDF页43-44）说明板载
USB-UART 芯片为 CP2102，FPGA_UART_TXD 对应 C24。配套 PG2L100H
`pg2l100h_remote_updata.fdc` 同时确认 C24、3.3 V、LVCMOS33。

| 端口 | 引脚 | 用途 |
| --- | --- | --- |
| clk | D18 | 27 MHz |
| rst_n | C22 | KEY0，低有效 |
| led_busy | A20 | LED0，计算忙 |
| led_done | C18 | LED1，计算完成 |
| led_pass | C19 | LED2，计算与捕获检查通过 |
| led_fail | E18 | LED3，计算或捕获失败 |
| uart_tx | C24 | FPGA → CP2102 → PC |

保持原 core27m.fdc，并添加 `constraints/fixed_slice_qwen_uart_io.fdc`。
UART 为 115200、8N1、无流控，27 MHz / 234 ≈ 115384.6 baud，误差约0.16%。
不接收主机指令或模型数据，不需要 UART RX。

## 已运行的验证

- `make lint-result-capture test-result-capture lint-fixed-slice-qwen-uart`：通过。
- `make lint-uart-board test-uart-board test-uart-board-overflow`：通过。
- 完整 TX 波形解码：256 条，2057 字节，每条与 PDS expected.mem 比较一致。
- 三次复位重跑、一次发送中复位恢复：通过。
- 深度255负向测试：保留255条、不覆盖、板级FAIL置位，仿真通过。
- `python3 scripts/verify_board_mem.py`：独立整数重算256条黄金值全部一致。
- `python3 scripts/run_regression.py`：17个阶段全部通过；机器可读结果在
  `build/reports/summary.json`，日志在 `build/reports/uart_full_regression.log`。
- 解码/接收器9个测试：负数、来源标记、错误帧、重复/越界标签、缺失记录、
  数值不符、分片与噪声、错误半帧后重新同步。
- 独立只读审查发现接收端遇到中断半帧时退出的问题，已修复并补充3个测试。

PDS 2022.2-SP6.4 / ADS 对当前工程实际运行：Compile、Synthesize、Device Map、
Place & Route、Report Timing、Generate Bitstream 均完成。

| 检查 | 结果 |
| --- | --- |
| 时序总评 | All Constraints Met |
| Clock Summary | 27 MHz，37.037 ns |
| 建立最差裕量 | 22.494 ns，0条失败 |
| 保持最差裕量 | Fast corner 0.057 ns，0条失败 |
| I/O | 7个，全部已分配，UART=C24 |
| LUT / FF | 1126 / 373 |
| APM / DRM | 16 / 8 |
| 捕获缓存 | 分布式RAM，256个RAM LUT，逻辑容量2KiB |

PDS 仍有无用调试寄存器移除、常量传播、扇出提示和异步IO接口时序提示。
UART TX 的单周期 max-delay 已进入时序报告；复位与 LED 路径按异步用途处理。
这些提示与最终时序结果共同核对，不能把“所有警告消失”作为通过条件。

## 位流

新文件：`fpgatest/qwen_slice/prj/generate_bitstream/fixed_slice_qwen_uart_board_top.sbit`

大小：3,791,112字节。SHA256：

```text
718330d02168d8a9af8ed09f5d24bc70e69eaad67431faef7639c3c7382eef16
```

原 `fixed_slice_qwen_demo_top.sbit` 已从 PDS 自动备份目录复制回原位置，
验证其 Git blob 与本次修改前 HEAD 一致，保留作 LED-only 回退基线。

## 板端验证步骤（已实际执行，可复现）

1. 连接板卡电源和 JTAG；另接扩展板 USB-UART Type-C 至电脑，确认出现
   Silicon Labs CP210x/CP2102 对应 COM 端口。COM1本身不证明板卡已连接。
2. 使用 PDS Configuration 把上述 UART 新位流下载到 FPGA。第一次先按KEY0
   再释放，检查 LED1/LED2为1、LED3为0。LED0可能因计算很快而看不到闪烁。
3. 本机已创建 `.venv-uart-win` 并安装 pyserial3.5，采集程序与串口枚举已测试。
   后续换电脑时，在 Windows 项目根目录首次安装可运行：

```powershell
python -m venv .venv-uart-win
.\.venv-uart-win\Scripts\python.exe -m pip install -r requirements-uart.txt
```

4. 本次CP2102为COM10；以后以实际枚举结果为准。在接收程序提示打开后再按KEY0：

```powershell
.\.venv-uart-win\Scripts\python.exe scripts/capture_result_uart.py --port COM10 --output artifacts/uart_board/run1.bin
```

该程序不向板卡写入数据，保存一帧原始二进制；拒绝覆盖已有采集文件。
不要同时用串口助手占用该端口。普通文本乱码不是接收失败，v1为二进制协议。

5. 导出并逐项核验：

```powershell
.\.venv-uart-win\Scripts\python.exe scripts/decode_result_uart.py artifacts/uart_board/run1.bin --source board --expected fpgatest/qwen_slice/prj/mem/expected.mem --rows 16 --groups 16 --output artifacts/uart_board/run1.json
```

6. 接收程序每次只收一帧；换成run2、run3重新打开，再分别按KEY0重跑。
   三帧均须2057字节、256条记录、全部黄金值一致，LED状态也须一致。
7. 给任务A：原始bin、JSON、所用sbit和SHA256、三次LED/复位记录。
   本协议未传输LED状态和位流标识，这两项必须在采集记录中另行注明。

## PDS 复现入口

当前工程已完成接入，无需再次添加源码。需要重新构建时在PDS Tcl Console运行：

```tcl
source D:/GPT/qiansai_FPGA/scripts/pds_uart_build.tcl
```

若从旧 LED-only 工程重建：先运行 `pds_uart_setup.tcl` 添加源码及补充约束，
然后在Sources树中右击 `fixed_slice_qwen_uart_board_top`，选择 Set As Top Module，
再运行构建脚本。脚本依据当前项目工作目录定位仓库；换盘路径时仅改source命令。

当前无 commit/push。仿真证据和真实板端采集应分开保存与标记。
