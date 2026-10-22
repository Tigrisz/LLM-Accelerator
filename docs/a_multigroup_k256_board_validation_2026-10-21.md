# A小用例K256：PDS与实板UART验证

日期：2026-10-21（北京时间）。工作分支：`codex/b-multigroup-uart-cases`。
**K256完整构建、位流下载及三次实板UART逐项比较均已通过。**
K384已接入独立工程并完成固定顶层仿真，但本轮没有构建或下载K384位流。
原Qwen工程及两份位流保持原样，未执行commit/push。

## 工程与数据

- K256：[a_multigroup_k256.pds](../fpgatest/a_multigroup_k256/prj/a_multigroup_k256.pds)。
- K384：[a_multigroup_k384.pds](../fpgatest/a_multigroup_k384/prj/a_multigroup_k384.pds)。
- 顶层分别为`a_multigroup_k256_uart_board_top`、`a_multigroup_k384_uart_board_top`。
- 两工程均明确选择PG2L100H-6FBG676、ADS、SystemVerilog；各自`prj/mem/`保存
  独立的三份.mem、config和manifest，4份输出文件哈希与转换清单匹配。
- N=3；K256分2组/行、捕获深度6；K384分3组/行、深度9。
- 原始数据来自A合成交接用例，seed=K；不是Qwen模型权重、不是模型端到端推理。

板级接口不变：D18/27MHz、C22/KEY0低有效复位，A20/C18/C19/E18分别为
busy/done/pass/fail，C24为UART TX；7个IO全部定位、LVCMOS33。
复用现有32路ROM打包到16路计算适配器，不修改原Qwen计算/UART RTL。

## PDS检查

官方`pds_shell -project ... -run gen_bit_stream`在独立目录完成：
Compile、Synthesize、Device Map、Place & Route、Report Timing、Generate Bitstream。
该次干净日志没有E或C级诊断；使用的是已选择ADS/SystemVerilog的.pds，
不使用首次建工程时带预解析错误的旧`-file`全流程日志作为验收依据。

| 项目 | K256结果 |
| --- | --- |
| 时钟 | 27 MHz / 37.037037 ns |
| 时序 | All Constraints Met |
| 最差setup / hold | 24.910 ns / 0.105 ns，失败端点0 |
| LUT / FF / Latch | 858 / 528 / 0 |
| APM / DRM | 16 / 2 |
| I/O | 7个全部定位，UART=C24 |
| RTL完整回归 | 19/19阶段通过 |
| Python测试 | WSL 55通过、3项Windows专用跳过；对应3项在Windows通过 |

实际PDS日志逐份确认读取本K256工程的weights/activation/expected.mem。
compile中的`Sdm-2003`只读ROM无运行时驱动提示没有伴随初始化丢失：
综合网表保留权重DRM的非零INIT参数、激活数据的初始化LUT，且本轮三次实板输出
均与原始整数golden匹配。此结论仅适用于已验证用例，不替代任意输入的形式等价证明。

异步复位和LED使用false-path；UART TX使用37.037037ns max-delay。
Timing-4086/4087的异步外部接口提示仍可出现，不虚构外部同步时钟以消除提示。

## 位流与下载

位流：[a_multigroup_k256_uart_board_top.sbit](../fpgatest/a_multigroup_k256/prj/generate_bitstream/a_multigroup_k256_uart_board_top.sbit)。
大小：3,791,112字节。SHA256：

```text
9f52c78c1d42c598e7e442aab9d7f15da7be9efe141a3d83aac228ecc26bb160
```

用户接回板卡后，实时枚举：CP2102 COM10（VID:PID=10C4:EA60，序列0001）；
FTDI下载器为COM8/COM9。只读JTAG扫描确认PG2L100H、ID=`0x00602899`。
下载前再次核验位流哈希，只写易失CRAM，不写Flash/eFuse。
下载done=1，状态=`0x081ffca0`，timeout/rbcrc/aut/crc/id错误位均0。
完整原始状态保留在program.log，不根据UART数据反推编程状态。

## 三次真实采集

每次先打开COM10接收，115200、8N1、无流控，程序不向板卡发送命令；
再由用户短按/释放KEY0。三次均6条、57字节，标签顺序和值全部一致：

| row_id | group_id | partial_sum |
| --- | --- | --- |
| 0 | 0 | -1284 |
| 0 | 1 | -920 |
| 1 | 0 | -3432 |
| 1 | 1 | 724 |
| 2 | 0 | -851 |
| 2 | 1 | 2890 |

run1/run2/run3原始帧逐字节相同，SHA256均为：

```text
028ca79b4385aa6ad78a08a066e02f72bef9cd0bccf67382dcdbc24c8106c577
```

每次均与PDS expected.mem、A原始expected_partial.npy及capture结果比较。
原包capture仅用于离线参考，本轮bin确实来自COM10串口，标记`source=board`。
用户三次确认LED1/LED2亮、LED3灭。LED状态和物理按键动作来自用户确认，
不是UART协议中的字段；协议也不携带位流ID，位流来源依赖下载日志与哈希链。

## 已冻结证据

[evidence/a_multigroup_pds/2026-10-21/k256](../evidence/a_multigroup_pds/2026-10-21/k256/)：

- `board/`：三次真实bin、解码JSON及A格式JSON。
- `bitstream/`：对应已下载位流的冻结副本。
- `rom/`：本轮使用的ROM、配置与转换manifest。
- `pds/`：干净构建日志、编译加载日志、时序/资源/引脚报告、扫描与下载记录。
- `rtl/`：最终19阶段回归日志、环境与源码指纹。
- `verification_manifest.json`：来源、三次LED确认、文件哈希与保护基线。

这些是当前未提交工作区实现的证据；HEAD基准为
`6c880d952ef7f54d01c94448dc0e4e1612258ced`，不声称该提交已包含本轮改动。
冻结证据中的日志路径保留运行时位置，以清单映射/实际目录读取。

## 如何重新打开和构建

PDS使用`File → Open Project`打开上面的K256 `.pds`，不要打开旧Qwen工程后改其顶层。
GUI窗口切换曾触发用户输入保护/最小化，因此本轮不宣称界面已自动显示新工程；
全部实际构建和检查均已有官方命令行证据。

Windows PowerShell从项目根执行：

```powershell
.\scripts\build_a_multigroup_pds.ps1 -K 256 -ValidateOnly
.\scripts\build_a_multigroup_pds.ps1 -K 256
```

入口显式绑定K256工程，不操作当前GUI中的其他工程；先检查ADS/SystemVerilog、
尺寸与ROM/config哈希。安装目录不同可传`-PdsShellPath`。
脚本返回PDS退出码；重新验收仍须检查新日志、时序和位流哈希，不能仅凭文件存在宣布通过。
首次创建用的`pds_a_multigroup_setup.tcl`不是完整重建入口；已经保存的两个.pds才是当前配置依据。

需要复现采集时，重新枚举串口，并在接收已打开后按KEY0：

```powershell
.\.venv-uart-win\Scripts\python.exe scripts/capture_result_uart.py --port COM10 --timeout 180 --max-records 6 --output artifacts/k256_new_run1.bin
.\.venv-uart-win\Scripts\python.exe scripts/decode_result_uart.py artifacts/k256_new_run1.bin --source board --expected fpgatest/a_multigroup_k256/prj/mem/expected.mem --rows 3 --groups 2 --output artifacts/k256_new_run1.json
```

不要同时用串口助手占用COM10；每次使用新文件名，不能覆盖旧采集。
K384下一步才运行其构建/时序/位流流程，再实际采集三次9条/81字节，不能沿用K256位流。

## 保留与审查边界

原Qwen .pds、LED-only和UART两份位流最终哈希均与执行前一致，给A的原回复文件也未修改。
独立审查提出的GUI活动工程误操作风险已修复；仅保留显式-project批处理入口，并补充测试。
按用户原选择沿用当前分支/目录，隔离在新增工程目录，代价是工作区仍含上一轮未提交文件。
本轮不做后综合形式等价、不做Qwen模型精度判断、不构建K384；不扩大固定用例验收结论。

延期Minor：PDS额外生成的`generate_netlist/`、`report_power/`和`flow.log`尚未加入忽略规则，
仅为缓存整理项，不影响本轮验证。后续提交前勿直接全量添加这些缓存；本轮没有commit/push。
