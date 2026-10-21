# 给任务A：Qwen UART实板结果交付说明

> 仓库归档入口：`deliveries/qwen_uart_board_handoff_2026-10-21.zip`，
> 三次原始数据及模型元数据另存到`evidence/uart_board/2026-10-21/`。
> 以下包内路径是固定ZIP内部的结构，与仓库归档路径不同；ZIP未重新打包。

日期：2026-10-21。交付对象：任务A。无需连接开发板即可先完成离线核验。

## 结论与适用范围

盘古100Pro+（MES2L676-100HP，PG2L100H）实际UART采集三次通过。
每次均由用户在接收打开后按KEY0复位触发，收到2057字节、256条记录，
全部row_id/group_id/partial_sum与同一份黄金值一致，三帧逐字节相同。
用户逐次确认LED1(done)/LED2(pass)亮、LED3(fail)灭。
LED状态不是从UART协议读取；原始帧也不携带位流ID。

这是固定数据的W4A8 GEMV模型切片验证，不是完整Qwen推理，不代表DDR吞吐或token/s。
本次未执行commit、push或远程发送；交付的是当前工作区的实测文件快照。
打包时仓库基线HEAD为`462caa31d13fd708c5d36dc4883e746547b4de86`，分支main；
UART工作尚未提交，不能把该HEAD称为包含UART改动的已提交版本。

## 数据集定义：先核对，勿与其他测试用例混用

| 项目 | 本包配置 |
| --- | --- |
| 模型 | Qwen/Qwen2.5-1.5B-Instruct |
| 层 / 模块 | layer 0 / self_attn.o_proj |
| 行 | rows_start=0，N=16 |
| 列 | cols_start=0，物理K=2048，原模型有效列1536，后512列补零 |
| 分组 | group_size=128，每行16组，共256条 |
| 标签 | row_id=0..15，group_id=0..15，当前顺序row-major/group-major |
| 计算并行度 | 16路；模型文件config.lanes=32表示存储打包宽度，不是计算路数 |
| 数据类型 | 权重INT4、激活INT8；部分和signed INT32 |
| 输入 | prompt="FPGA W4A8 slice validation."，token_index=-1 |

最后4组group_id=12..15为补零组，各行部分和均为0；这仍是应被读回和核验的有效记录，
不能因其数值为0而丢弃。首项(0,0,145)，末项(15,15,0)。

## 包内文件与用途

包内保留原仓库相对路径，解压后以包含本README.md的目录作为根目录。

- `artifacts/uart_board/2026-10-21/run1.bin`至`run3.bin`：COM10真实板端原始帧。
- 同目录`run1.json`至`run3.json`：256条三元组及source=board、verification.passed=true。
- 同目录`verification_manifest.json`：三次接收时间、LED反馈、端口、位流与.mem校验值。
  其中run文件名相对于该manifest所在目录，其余file字段相对于解压根目录。
- 同目录`program.log`：官方工具实际JTAG下载日志，只配置FPGA CRAM，未写Flash/eFuse。
- `fpgatest/qwen_slice/prj/generate_bitstream/fixed_slice_qwen_uart_board_top.sbit`：对应UART位流。
- `fpgatest/qwen_slice/prj/mem/{weights,activation,expected}.mem`：与该位流关联的初始化数据和黄金值。
- `build/model_slices/qwen_o_proj_l0_k2048/`：配置、打包权重、激活、量化尺度、期望部分和。
  打包前已核对这些数据与PDS的三个.mem逐项对应。
- `docs/uart_board_capture_2026-10-21.md`：实际下载、驱动排查、三次实板验证报告。
- `docs/uart_board_validation_2026-10-21.md`：板级接入、引脚、PDS资源/时序及复现步骤。
- `docs/result_capture_uart_v1.md`：UART二进制协议说明。
- `scripts/decode_result_uart.py`：仅用Python标准库即可离线重解码、比较，无需Torch。
- `scripts/verify_board_mem.py`：从.mem解包INT4/INT8并独立整数重算黄金值。
- `scripts/capture_result_uart.py`和`requirements-uart.txt`：可选的重新采集工具及pyserial依赖。
- `SHA256SUMS.txt`：包内全部交付文件校验值；不包含该清单自身。

这是结果验收包，不是完整PDS可重新综合工程；无需将包内build目录覆盖到现有工程。
构建源码、完整PDS工程仍在任务B工作区。本包位流可直接用于同型号同接线板卡复测。
`artifacts/`、`build/`在原仓库被Git忽略，不影响本ZIP的完整交付。

## A的第一步：独立确认交付完整性

先保留ZIP和原始bin不变，解压到独立目录。Windows PowerShell进入解压根目录：

```powershell
$hashFailures = @()
Get-Content SHA256SUMS.txt | ForEach-Object {
    $hashParts = $_ -split '  ', 2
    $actualHash = (Get-FileHash -LiteralPath $hashParts[1] -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $hashParts[0]) { $hashFailures += $hashParts[1] }
}
if ($hashFailures.Count) { throw ('校验失败：' + ($hashFailures -join ', ')) }
'SHA256全部一致'
```

Linux/WSL可在同一目录运行`sha256sum -c SHA256SUMS.txt`。
ZIP自身的SHA256在ZIP旁同名`.zip.sha256`文件中，用于传输后确认ZIP未变。

## A的第二步：从原始bin重新解码并逐项验证

使用Python 3.10或更新版本，在解压根目录运行。Windows若命令名为python3，
自行把下面python替换为python3；此步骤不需要安装pyserial或NumPy。
使用新的输出文件名，保留B交付的JSON作为原始记录。

```powershell
1..3 | ForEach-Object {
    python scripts/decode_result_uart.py "artifacts/uart_board/2026-10-21/run$_.bin" --source board --expected fpgatest/qwen_slice/prj/mem/expected.mem --rows 16 --groups 16 --output "artifacts/uart_board/2026-10-21/a_recheck_run$_.json"
    if ($LASTEXITCODE -ne 0) { throw "run$_ 验证失败" }
}
```

应三次正常退出，JSON中count=256、verification.passed=true。
解码器会拒绝数量不符、重复/越界/缺失标签及partial_sum不符。
SHA256也应三次相同：

```text
410f0086fa79888f974e245f9ac878eaad452fdd9ee3adc5eb3f62f484077cf0
```

不要只检查JSON里已有的passed字段，应以上述重新解码比较为准。
`--source board`是来源标签，不是硬件来源的密码学证明；来源还依赖实际采集记录。

## A的第三步：接入现有验算/联调流程

1. 从run1.json读取`records`，以(row_id,group_id)为键建立完整16×16表，
   将partial_sum按signed INT32处理。可选用run2/run3复核复位稳定性。
2. 与本包expected.mem或expected_partial.npy比较；mem索引为row_id*16+group_id，
   文本十六进制值须按32位补码解释。必须检查所有标签，不能仅比较最后一个结果。
3. 若A有独立Python/RTL参考模型，使用本包weight_packed.bin和activation_int8.bin，
   保持已有打包及W4A8约定，重算本用例的256条部分和；不要使用其他用例的golden。
   也可先运行`python scripts/verify_board_mem.py`，应显示PASS BOARD_MEM并生成
   `build/reports/board_mem.json`；该工具在无PDS config时推断物理K，不能代替
   模型config中的source_cols=1536元数据。
4. 如需量化近似浮点输出，可用scales.npy[16,16]和activation_scale.npy标量：
   `y_hat[row] = sum(partial_sum[row,group] * scales[row,group] * activation_scale)`。
   先逐组乘权重尺度再累加；不能先把不同尺度的INT32组和简单相加再乘一个尺度。
   读取.npy需要NumPy。该输出只是所选16行、单token输入的量化近似结果，不是完整层输出。
5. 请A回传：本包名称/位流SHA256、离线核验结论、独立golden比较结论；如不一致，
   返回第一个(row_id,group_id)、期望值和板端值，保留原始bin供B排查。

## 后续与B联调：按用例逐步扩展

本包先作为“N16、有效1536列/物理K2048、UART实测三次稳定”的基线。
A之前交付的lanes16_n3_k256和lanes16_n3_k384是另外两套离线RTL用例，
应分别输出6条和9条，不能用本包256条结果冒充那两个用例已上板通过。

下一轮建议A/B先共同冻结用例名称、N/K、分组、打包和黄金文件SHA256；
B再替换对应.mem、配置N/K/捕获深度，重新综合/布局布线/生成并下载对应新位流，
重复三次复位与UART逐项核验，再由A用各用例自己的golden验收。
当前位流固化了N16/K2048及初始化数据，不能通过串口命令动态切换到N3用例。

如果A需要自行复测当前用例：在同型号开发板下载本包.sbit（PDS Configuration，
FPGA CRAM Program），按实际枚举选择CP2102端口。COM10只适用于本次电脑快照。
关闭串口助手对该端口的占用，安装`requirements-uart.txt`后打开接收，再按KEY0。
不要把JTAG下载器的FTDI双串口当作CP2102。

v1没有CRC、LED状态或位流ID字段。离线验收依赖整帧、完整黄金值比较、校验清单
与下载/用户观察记录；不把UART发送耗时当作计算性能。
