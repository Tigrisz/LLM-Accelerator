# UART 实板下载与采集记录（2026-10-21）

> Git提交归档：原始数据/JSON/manifest/下载日志已另存到
> `evidence/uart_board/2026-10-21/`；交付包另存到`deliveries/`。
> 下文artifacts路径保留为实际采集时的位置，原文件和固定交付ZIP未改写。

## 已完成

通过 PDS 2022.2-SP6.4 自带 `cdt_cfg_shell.exe` 扫描并下载新位流至 FPGA CRAM。
未执行 Flash、eFuse 或密钥操作。

- JTAG cable：PANGO USB CABLE II。
- 器件：PG2L100H；ID：`0x00602899`。
- 位流：`fpgatest/qwen_slice/prj/generate_bitstream/fixed_slice_qwen_uart_board_top.sbit`。
- SHA256：`718330d02168d8a9af8ed09f5d24bc70e69eaad67431faef7639c3c7382eef16`。
- 官方工具输出：`The done bit is 1`、`COMMAND[Program] execute successfully`。
- 状态寄存器：`0x081ffca0`；done=1、init_complete=1，crc_err/aut_err/id_err均为0。
- 本次下载日志：`artifacts/uart_board/2026-10-21/program.log`。
- 复现脚本：`scripts/pds_uart_program.tcl`（当前仓库绝对路径；换路径须相应调整）。

注意：FPGA配置寄存器的done只证明配置完成，不等同于用户逻辑led_done/led_pass。
三次KEY0复位后的实物LED状态由用户逐次确认，详见下方采集记录；
不把配置寄存器的done替代用户逻辑的计算结果。

## UART 连接排查（历史过程）

用户说明下载器、UART的Type-C线都已连接。系统只枚举出：

| 端口 | 硬件标识 | 判断 |
| --- | --- | --- |
| COM1 | ACPI PNP0501 | 系统通信端口 |
| COM6 | FTDI 0403:6010 | 下载器双通道之一 |
| COM7 | FTDI 0403:6010 | 下载器双通道之一 |

未枚举出手册所述 CP2102；也未发现缺驱动的 CP2102/未知USB错误设备。
用户只拔下UART线、保留下载器后，COM6/COM7及其USB设备完全不变，
因此这两个端口不是被拔下的板载UART接口。不能通过修改串口助手选择来替代
硬件设备枚举。

用户反馈已换线接回后再次检测，结果仍为COM1/COM6/COM7，CP2102尚未出现。
检查当前存在的设备，未发现未知USB设备或缺驱动的CP2102记录。现有证据只
定位到UART的USB枚举尚未完成，不能确定是接口位置、线缆/USB口兼容性、
供电或板卡UART硬件的哪一项原因。

用户提供整体与局部照片后，确认白色线插入J17（UART），旁边U9为CP2102；
板卡POWER灯与核心板指示灯点亮。照片中LED1、LED2亮，LED0、LED3灭，
与该位流的完成/PASS显示一致（单张照片快照，不替代UART数值采集）。
收到照片后重新枚举仍未发现CP2102。照片未显示白色线的电脑端连接位置，
下一步核对该端是否直连电脑USB数据口，以及USB-A/Type-C/扩展坞连接方式。

## 驱动安装后的实际板端采集

2026-10-21重新枚举确认：Silicon Labs CP210x USB to UART Bridge **COM10**，
VID:PID=`10C4:EA60`、序列号`0001`，设备类别Ports、状态OK。
FTDI下载器当前为COM8/COM9，不用于本次UART接收。端口号换USB口后可能变化。

使用Windows `.venv-uart-win/Scripts/python.exe` 运行现有接收脚本，
115200 baud、8N1、无流控。每轮先打开COM10，再由用户短按并释放KEY0。
主机仅被动接收，没有向FPGA发送模型数据或计算结果，也未以仿真文件代替采集。

| 轮次 | 接收完成时间（北京时间） | 字节 / 记录 | 三元组比较 | 用户确认LED状态 |
| --- | --- | --- | --- | --- |
| run1 | 18:45:09 | 2057 / 256 | 全部一致 | LED1/LED2亮、LED3灭 |
| run2 | 18:45:46 | 2057 / 256 | 全部一致 | LED1/LED2亮、LED3灭 |
| run3 | 18:46:51 | 2057 / 256 | 全部一致 | LED1/LED2亮、LED3灭 |

用户确认第一帧由其KEY0操作触发，并分别确认后两次复位及LED状态。
每轮均核验row_id=0..15、group_id=0..15的全部256种组合，无重复、缺失或越界；
记录顺序为row-major/group-major，所有有符号32位partial_sum与
`fpgatest/qwen_slice/prj/mem/expected.mem`对应项一致。首项(0,0,145)，
末项(15,15,0)。三次原始帧逐字节相同。

数据目录：`artifacts/uart_board/2026-10-21/`。

- `run1.bin`、`run2.bin`、`run3.bin`：COM10实际接收的原始二进制帧。
- `run1.json`、`run2.json`、`run3.json`：逐项结果，source=board，verification.passed=true。
- `verification_manifest.json`：端口、位流/初始化文件校验值、三次复位验证及来源。
- `program.log`：此前实际下载记录，本次未重新构建或重新下载位流。

三份原始帧的SHA256均为：

```text
410f0086fa79888f974e245f9ac878eaad452fdd9ee3adc5eb3f62f484077cf0
```

本次重新计算位流SHA256，与此前实际下载记录一致。帧协议本身不携带位流ID或
LED状态：位流关联依赖下载记录，LED依据用户反馈，不声称从UART直接读取。
`artifacts/`已被.gitignore忽略，后续提交时应另外打包交付原始数据，不会自动纳入Git。

## 当前验收状态

- 新位流下载：通过。
- 板端UART原始数据：COM10实际采集三帧，通过。
- 每轮256条row_id/group_id/partial_sum逐项比较：三轮全部通过。
- 三次KEY0复位重跑：通过，三帧逐字节一致。
- 实物LED状态：用户逐轮确认LED1/LED2亮、LED3灭；LED0未逐轮记录。

没有以仿真capture替代真实板端数据；未执行commit或push。
