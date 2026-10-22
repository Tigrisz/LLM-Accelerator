# A小用例K384：PDS与三次实板UART验证

日期：2026-10-21（北京时间）。分支：`codex/b-multigroup-uart-cases`。

K384已完成编译、综合、映射、布局布线、时序检查、位流生成、CRAM下载及三次实板采集。
三次均9条/81字节，row_id、group_id、partial_sum全部匹配，三帧逐字节相同。
原Qwen、K256工程/ROM/约束/位流及K256冻结证据按本轮执行前77份文件哈希保护。
没有commit或push，也没有修改现有计算/UART RTL。

## 工程、配置和本轮修复

工程：[a_multigroup_k384.pds](../fpgatest/a_multigroup_k384/prj/a_multigroup_k384.pds)。
顶层：`a_multigroup_k384_uart_board_top`。器件：PG2L100H-6FBG676，ADS、SystemVerilog。
N=3、K=padded_K=384、group_size=128、每行3组、CAPTURE_DEPTH=9。
仍使用B现有32路ROM打包→16路计算适配器，三个初始化文件来自本工程`prj/mem/`。
原始A输入是确定性合成整数用例（seed=384），不是Qwen模型切片。

首次构建发现`C: Bitstream-2001`：K384工程未设置SCBV。
即使工具退出码为0且输出了.sbit，该轮也没有用于下载。
按调试技能比对同板已验收Qwen/K256工程后，仅在K384 `.pds`补入：

```text
cmd_gen_bitstream: scbv = High Voltage
cmd_compile: force_to_run = ON
```

随后重新运行完整流程。最终验收日志没有E/C级诊断，SCBV警告消失。
初次有警告的日志单列为`build_initial_scbv_unset.log`，不是通过凭证。
High Voltage只对应当前已核验板卡配置；换板必须重新确认配置bank电压。

## 构建与检查结果

| 检查 | K384结果 |
| --- | --- |
| Compile / Synthesize / Device Map | 全部完成 |
| Place & Route / Timing / Bitstream | 全部完成 |
| 时钟 | 27 MHz，37.037037 ns |
| 时序汇总 | All Constraints Met |
| 最差setup / hold裕量 | 24.087 ns / 0.103 ns，失败端点0 |
| LUT / FF / Latch | 917 / 613 / 0 |
| APM / DRM | 16 / 2 |
| I/O | 7个全部定位，UART TX=C24 |
| 完整回归 | 19/19阶段通过 |
| Python测试 | WSL 55通过、3项Windows专用跳过；对应3项Windows测试通过 |

引脚继续为：clk D18、KEY0/rst_n C22、busy A20、done C18、pass C19、fail E18、UART TX C24。
PDS日志逐一确认读取本K384工程的weights.mem、activation.mem、expected.mem，未串用K256数据。
4份ROM/config输出哈希与转换manifest匹配，原打包INT4×INT8输入独立重算9条golden也匹配。

保留的已处置提示包括只读初始化ROM无运行时驱动、无用调试信号移除和异步外部接口提示。
KEY0/LED有false-path，UART TX有37.037037ns max-delay；内部时序满足。
本轮实板输出进一步验证固定输入的初始化和计算行为，不作任意输入后综合形式等价声明。

## 位流及下载

位流：[a_multigroup_k384_uart_board_top.sbit](../fpgatest/a_multigroup_k384/prj/generate_bitstream/a_multigroup_k384_uart_board_top.sbit)。
大小：3,791,112字节。最终SHA256：

```text
357bd0201b621faf553c3c46b3d750c9e3bc23348252c258f6029f14fe7efb94
```

下载前再次核验该哈希，JTAG扫描确认PG2L100H、ID=0x00602899。
官方配置工具只写易失CRAM，不写Flash/eFuse；下载done=1，状态0x081ffca0，
timeout/rbcrc/aut/crc/id错误位均0。完整状态位保留在下载原始日志中。
当前板卡运行K384；原Qwen和K256文件仍保留，未重新下载或改写那些工程。

## 三次实际UART结果

实时串口：CP2102 COM10，VID:PID=10C4:EA60、序列0001；FTDI下载器COM8/COM9。
115200、8N1、无流控，每次先打开被动接收，再由用户短按并释放KEY0。
每次得到如下9条，逐项与PDS expected.mem、A原npy、原始打包重算及A仿真参考匹配：

| row_id | group_id | partial_sum |
| --- | --- | --- |
| 0 | 0 | -6908 |
| 0 | 1 | 1686 |
| 0 | 2 | -1175 |
| 1 | 0 | -1560 |
| 1 | 1 | -1043 |
| 1 | 2 | -3218 |
| 2 | 0 | -4489 |
| 2 | 1 | 215 |
| 2 | 2 | 1156 |

run1、run2、run3各81字节，SHA256均为：

```text
9e0277e49852d894561765c6f4896fbb19ad953bb6ee5d23e27c42395151eda4
```

三次用户均确认LED1/LED2亮、LED3灭。该LED/按键记录来自用户确认，不是协议字段。
UART协议也不包含位流ID；位流身份由下载日志、路径和编程前哈希核验关联。
本轮bin是实际COM10采集，标记`source=board`；原包capture及RTL模拟输出仍是simulation，
即使字节相同也不能互换来源。

## 文件位置与复现

已冻结到[evidence/a_multigroup_pds/2026-10-21/k384](../evidence/a_multigroup_pds/2026-10-21/k384/)：

- `board/`：3份原始bin、解码JSON、A格式JSON。
- `bitstream/`：对应下载位流的冻结副本。
- `rom/`：本轮ROM、config及转换manifest。
- `pds/`：最终构建日志、SCBV初次诊断、资源/时序/引脚报告、扫描/下载记录及保护基线。
- `rtl/`：19阶段回归日志、源码指纹及环境。
- `verification_manifest.json`：数据来源、三次确认、哈希和保护结果。

从Windows项目根重建：

```powershell
.\scripts\build_a_multigroup_pds.ps1 -K 384 -ValidateOnly
.\scripts\build_a_multigroup_pds.ps1 -K 384
```

入口显式选择独立K384 `.pds`，不会操作GUI当前打开的其他工程。
仍须检查新日志、SCBV、时序和位流哈希，不能只凭退出码或文件存在宣布通过。
如需GUI查看，用File → Open Project打开K384工程；本轮不强行切换GUI窗口。

再次采集需选择新文件名，并先确认当前真实串口号：

```powershell
.\.venv-uart-win\Scripts\python.exe scripts/capture_result_uart.py --port COM10 --timeout 240 --max-records 9 --output artifacts/k384_new_run1.bin
.\.venv-uart-win\Scripts\python.exe scripts/decode_result_uart.py artifacts/k384_new_run1.bin --source board --expected fpgatest/a_multigroup_k384/prj/mem/expected.mem --rows 3 --groups 3 --output artifacts/k384_new_run1.json
```

不要让串口助手同时占用COM10。仅运行接收命令不会复位板卡，需要接收打开后按KEY0。

## 边界及保留策略

沿用用户已选当前分支/目录，保持原Qwen和K256内容不变；代价是工作区仍含前几轮未提交文件。
本轮只修改K384工程配置、生成其构建/采集证据；没有改变计算行为。
SCBV修复遵循同一板卡已验收配置，不推广到不同电压板卡。
测试仅证明固定合成用例，不代表Qwen端到端模型推理、任意输入形式等价或完整模型精度。
既有生成缓存整理项仍延期；提交前应按清单整理，不要直接全量添加PDS缓存。

独立只读审查结论PASS，无Critical/Important：49份冻结证据、141项回归源文件指纹、
77份Qwen/K256保护文件均独立核验无差异；原始打包重算、NPY和三帧UART也全部匹配。
延期Minor仅为每轮接收命令输出/操作确认的精确时间戳日志增强；不补造历史时间戳。
板端来源仍依本次实际串口会话和用户确认，不能从与仿真相同的字节反推来源。
没有独立测量配置bank电压或解释状态字中的over_temp字段，也未做温度或完整电气验收；
完整原始状态保留在program.log。本轮没有核验远程同步状态，未执行commit/push。
