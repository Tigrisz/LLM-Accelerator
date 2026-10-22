# 给任务A：同一Qwen切片浮点参考与量化误差核验

打包日期：2026-10-22。ZIP：`qwen_float_handoff_2026-10-22.zip`，请与同名`.zip.sha256`一起接收。
本包新增的是离线浮点重放和误差评估；引用的三次原始UART仍为2026-10-21的实板采集，未重新上板。

## 1. 交接结论

固定checkpoint：`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`，模型`Qwen/Qwen2.5-1.5B-Instruct`。
layer0 `self_attn.o_proj`，前16行，cols_start=0，有效1536列/物理K2048，group_size=128。
prompt=`FPGA W4A8 slice validation.`，token_index=-1，与已验收Qwen采集一致。

原模型权重与捕获激活为BF16，**在W4A8量化前转FP32保存**。
这是原加载精度的数据副本，不是FP32模型重推理，也不是从INT4/INT8反量化构造的“原始参考”。
主浮点参考为这些保存值的FP64点积，无bias（该层实际无bias）；还提供FP32点积作辅助比较。

重新量化的5份载荷及3份ROM与原归档逐字节相同；三份原始UART各256条结果全部一致。
16个行输出的量化误差为：

| 指标 | 结果 |
| --- | ---: |
| 最大绝对误差 | 0.07159525168142564 |
| MAE | 0.024767229797858142 |
| RMSE | 0.03205080543799835 |
| 相对L2误差 | 0.09709669613175766（约9.71%） |
| 最大逐行相对误差 | 0.6378852652394903（约63.79%） |
| 余弦相似度 | 0.995490454229897 |

`status=pass`只表示数据对应关系与评估执行通过；尚未约定精度阈值，不能据此宣称模型精度通过。
这是单层/单prompt/token的16行切片，不是完整模型、DDR或吞吐性能验收。

## 2. 包内结构和范围

```text
README.md                                    本核验说明
handoff_manifest.json                        整包载荷哈希与来源索引
SHA256SUMS.txt                               所有载荷及handoff_manifest的校验清单
evidence/qwen_float/2026-10-22/               本轮浮点参考、误差报告和冻结验证记录
  reference/                                weights/activation FP32、FP64/FP32参考、manifest
  evaluation/                               summary、反量化输出、重建量化输入和ROM
  validation/                               19阶段回归、Windows测试、旧文件保护清单
evidence/uart_board/2026-10-21/               原三次UART、JSON、原量化数据与采集清单
evidence/model_provenance/2026-10-21/         原固定checkpoint来源与重放记录
fpgatest/qwen_slice/prj/mem/                  原三份ROM
fpgatest/qwen_slice/prj/generate_bitstream/   原Qwen UART对应.sbit（只供核对，无自动下载）
model/                                      核验和提取所需Python模块
scripts/                                    误差审计、原提取、ROM准备及UART解码脚本
tests/test_qwen_float_reference.py           11项新增测试
docs/qwen_float_reference_2026-10-22.md       详细报告、环境和固定snapshot重放命令
```

不包含数GB checkpoint、虚拟环境、完整RTL/PDS工程或K256/K384工程；本包是数据/核验工具交接包。
完整工程仍在仓库。旧报告/`protected_files.json`可能列出未打包的K256/K384或原仓库路径，
它们是原工作区保护/溯源记录，不是本包的缺件；包内文件范围以根校验清单为准。
`regression/environment.json`包含完整仓库源码指纹，不表示本包能重新执行整套HDL回归。

本轮工作基准HEAD为`44544a58ad65a4bb383608a9f403b12b82d70376`，新增浮点工作尚未提交。
已获取并检查main=`29211823da7cb6b07e13a7affbe2d1989abdfc8f`，未自动合并。
本包不声称上述旧提交已包含新增浮点代码；请按包内SHA256确定当前文件版本。

## 3. 先检查传输与包内哈希

Linux/WSL，在ZIP旁执行：

```bash
sha256sum -c qwen_float_handoff_2026-10-22.zip.sha256
```

解压到新目录，进入包含README.md的包根目录后：

```bash
sha256sum -c SHA256SUMS.txt
```

Windows PowerShell：先用`Get-FileHash .\qwen_float_handoff_2026-10-22.zip -Algorithm SHA256`
人工核对同名`.zip.sha256`；进入解压包根目录后执行：

```powershell
Get-Content .\SHA256SUMS.txt | ForEach-Object {
    $auditParts = $_ -split '  ', 2
    $auditHash = (Get-FileHash -LiteralPath $auditParts[1] -Algorithm SHA256).Hash
    if ($auditHash -ne $auditParts[0]) { throw "Hash mismatch: $($auditParts[1])" }
}
'PASS package hashes'
```

哈希提供完整性检查，不是数字签名，也不能独自证明历史硬件采集来源。

## 4. 无需PDS、开发板和Torch的完整数值核验

需要Python 3.10+及NumPy。B原提取/审计环境为NumPy2.5.4，建议使用相同版本。
核验只读取包内证据；输出使用包外一个**不存在**的新目录，不覆盖冻结报告：

```bash
python3 scripts/evaluate_qwen_quantization.py \
  --reference evidence/qwen_float/2026-10-22/reference \
  --output ../qwen_float_task_a_audit_new
```

完整逐字节ROM核验请在Linux/WSL运行。Windows可执行前述哈希检查和下述单元测试；
原ROM准备脚本在Windows会生成CRLF，直接运行完整审计可能触发ROM行尾哈希不一致，
不能因此放宽数值比较或覆盖原ROM。
重复执行请更换输出目录，脚本拒绝覆盖或写入输入目录。
脚本会检查：

1. 浮点清单必须包含全部5个NPY，并逐项核对哈希、形状、dtype和零填充。
2. checkpoint revision及7份模型/tokenizer文件哈希与旧来源记录一致。
3. 原浮点值重新量化，5份载荷与旧归档逐字节一致；三份ROM同样逐字节一致。
4. 原始UART三帧的哈希、数量、标签、顺序、256项INT32结果一致。
5. 逐组反量化与独立逐元素重建吻合，再与原始浮点参考计算误差。

审计报告写在指定目录的`summary.json`，应与包内
`evidence/qwen_float/2026-10-22/evaluation/summary.json`一致。
原`.sbit`应与`evidence/uart_board/2026-10-21/verification_manifest.json`中的哈希一致：

```text
718330d02168d8a9af8ed09f5d24bc70e69eaad67431faef7639c3c7382eef16
```

补充运行测试，在包根目录执行：

```bash
python3 -m unittest discover -s tests -p test_qwen_float_reference.py
```

预期11项通过。测试仅使用合成小数组，不加载模型，不访问串口，不运行PDS。

## 5. 从checkpoint重放（可选）

普通数值核验无需模型；若要独立确认checkpoint原始浮点来源，再按详细报告的固定snapshot命令，
安装对应Torch/Transformers环境，运行包内`extract_qwen_slice.py --float-reference-output ...`。
模型、tokenizer和推理设置均需固定；使用新输出目录，禁止覆盖已验收量化数据。
原加载为BF16；不要改成FP32推理后要求激活与旧板端量化输入逐字节匹配。
读取保存的浮点参考重算，只证明文件内部数值一致，不等于已经独立重放了模型。

## 6. 建议任务A返回的结论

请分别反馈ZIP/成员哈希、checkpoint来源记录、5份量化载荷/3份ROM、三次UART及浮点误差重算是否通过。
同时注明是否实际加载checkpoint；不要将“只核对元数据哈希”写成“已独立重放模型”。
相对L2定义为`||y_quant-y_float||2 / ||y_float||2`，最大逐行相对误差对
`abs(y_float)>1e-12`的行计算；本次未排除行。最大绝对误差为row9，最大相对误差为row15。
需另行约定代表性prompt/token集合及精度阈值；不能只看余弦相似度就忽略部分行较大的相对误差。

现有工程、位流、旧证据不变；本次没有commit或push，也没有重新采集UART。
