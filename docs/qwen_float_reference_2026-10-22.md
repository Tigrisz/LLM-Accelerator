# B：同一Qwen切片的原始浮点参考与量化误差评估

日期：2026-10-22（Asia/Shanghai）。本轮无新上板采集，不修改原Qwen、K256、K384工程/ROM/位流。

## 1. 最新main检查与工作分支

通过SSH执行`git fetch git@github.com:Tigrisz/LLM-Accelerator.git main`，
本轮获取的main为`29211823da7cb6b07e13a7affbe2d1989abdfc8f`，与A留言一致。
它包含PR #6、A的UART独立验收和逐组反量化一致性检查。
本地仍在`codex/b-multigroup-uart-cases`，HEAD为`44544a58ad65a4bb383608a9f403b12b82d70376`；
相对于获取的main，本地独有1个提交、main独有11个提交。

检查发现A新增`audit_uart_delivery.py`、`compare_results.py`等工具、UART验收回归阶段和
小范围兼容性/报告输出修复；没有改变本轮沿用的模型提取和W4A8量化算法。
本轮只获取和检查，**没有自动merge/rebase/main切换，也未commit或push**。
下述回归是在当前B分支加本轮未提交改动上运行，不冒称已在合并后的main上重跑。
`FETCH_HEAD`是本轮获取记录；没有改写origin的HTTPS配置。

## 2. 与已验收板端数据的对应关系

- 模型：`Qwen/Qwen2.5-1.5B-Instruct`。
- 固定revision：`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`。
- 层/模块：layer0，`self_attn.o_proj`；rows_start=0，N=16，cols_start=0。
- 有效输入宽度1536；物理K2048；末尾512列权重和激活均为0。
- prompt：`FPGA W4A8 slice validation.`；token_index=-1，输入token ID和mask已保存。
- CPU、eval、no_grad、use_cache=False，沿用原`torch_dtype="auto"`加载流程。
- 原权重和捕获激活实际dtype均为BF16，转FP32后保存；不是将模型改成FP32重新推理。
- `o_proj`本次无bias；浮点参考定义为`W @ x`，不含bias，与整数GEMV口径一致。

checkpoint的7份模型/tokenizer文件哈希全部匹配已验收的
`evidence/model_provenance/2026-10-21/provenance.json`，包括：

```text
model.safetensors SHA256:
dd924a11b4c220f385b51ffa522daea7c9f3d850e31b162bb5661df483c6d3ee
```

该版本记录的实际依赖：Python3.14.4、torch2.14.1+cu130、transformers5.20.1、numpy2.5.4；
完整版本、checkpoint哈希、脚本哈希、输入token见新参考的`manifest.json`。

## 3. 新生成资料

根目录：`evidence/qwen_float/2026-10-22/`。

| 相对该根目录路径 | 内容 |
| --- | --- |
| `reference/weights_fp32.npy` | [16,2048]，量化前权重，含512列0填充 |
| `reference/activation_fp32.npy` | [2048]，同一token的量化前激活，含512个0 |
| `reference/reference_groups_fp64.npy` | [16,16]，原始浮点逐128元素分组点积 |
| `reference/reference_fp64.npy` | [16]，FP64乘法/分组归约/行归约的主参考 |
| `reference/reference_fp32.npy` | [16]，同一保存值使用NumPy FP32矩阵乘的辅助参考 |
| `reference/manifest.json` | 维度、来源、dtype、参数、token、环境及数组SHA256 |
| `evaluation/summary.json` | 重新量化、ROM、三次UART、来源检查及逐行误差 |
| `evaluation/dequantized_fp64.npy` | 已验收整数部分和按行/组尺度反量化的输出 |
| `evaluation/requantized/` | 从新浮点数据重新生成的量化载荷，仅供审计，不替换板端输入 |
| `evaluation/requantized_mem/` | 从审计载荷生成的三份ROM，仅供逐字节比对 |
| `validation/` | 本轮回归结果、来源检查和旧文件保护记录 |
| `SHA256SUMS.txt` | 本目录文件的冻结校验清单，不包含其自身 |

上述权重/激活来自checkpoint前向和目标层pre-hook，不是通过INT4/INT8反量化构造。
主参考由保存的量化前FP32值使用FP64重新计算；不声称等于BF16目标层原生kernel的舍入输出。
该检查只对应一个prompt/token和16行，不是完整1536行输出，也不是完整模型精度测试。

## 4. 一致性检查

1. checkpoint revision与7份文件SHA256匹配原来源记录。
2. 量化前数据按原算法重新量化，以下5份文件与旧归档**逐字节一致**：
   `weight_packed.bin`、`activation_int8.bin`、`scales.npy`、`activation_scale.npy`、`expected_partial.npy`。
3. 新生成的`weights.mem`、`activation.mem`、`expected.mem`与原Qwen PDS ROM逐字节一致。
4. 从旧`run1/2/3.bin`重新解码，检查SHA256、数量、顺序、row/group标签和全部256条INT32部分和。
5. 逐组反量化`sum_g(partial[r,g] * weight_scale[r,g] * activation_scale)`，
   与独立的反量化逐元素矩阵乘在`rtol=atol=1e-12`下相符；三次结果一致。

旧原始数据位于`evidence/uart_board/2026-10-21/`，没有新增或伪造一次硬件采集。
UART v1不含位流ID、CRC或LED字段；来源关联仍基于原采集记录、下载日志和清单。

## 5. 量化误差结果与解释

误差对象：16个行输出，即“原始量化前切片的FP64参考”与“已验收板端整数结果反量化”。

| 指标 | 数值 |
| --- | ---: |
| 最大绝对误差 | 0.07159525168142564 |
| MAE | 0.024767229797858142 |
| RMSE | 0.03205080543799835 |
| 相对L2误差 | 0.09709669613175766，约9.71% |
| 最大逐行相对误差 | 0.6378852652394903，约63.79% |
| 余弦相似度 | 0.995490454229897 |

相对L2定义为`norm(y_quant-y_float)/norm(y_float)`，不是MAE百分比。
逐行相对误差仅对`abs(y_float)>1e-12`的行计算；本次没有排除行。
全零参考范数时相对L2返回JSON null而不是NaN/Infinity。
最大绝对误差位于row9；最大逐行相对误差位于row15，原值约-0.07249，量化值约-0.02625。
因此不能只看余弦相似度就宣称所有行误差很小。

辅助FP32参考与FP64主参考的最大绝对差约`2.0610e-7`，远小于本次量化误差。
权重/激活重建误差和全部逐行结果也保存在`summary.json`。
报告`status=pass`表示数据对应关系与评估流程通过，不代表模型精度达到某个未约定阈值。
尚无量化误差验收阈值，后续由A/B确定代表性prompt/token集合和目标指标，再决定是否改变量化方案。

## 6. 复现命令

在WSL、仓库根目录执行，使用已有原环境。模型已缓存，命令不访问可变远程main：

```bash
cd /mnt/d/GPT/qiansai_FPGA
source .venv-qwen/bin/activate
SNAPSHOT=/home/jack/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct/snapshots/989aa7980e4cf806f80c7fef2b1adb7bc71aa306

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python scripts/extract_qwen_slice.py \
  --model "$SNAPSHOT" \
  --output build/qwen_float_replay_new/quantized \
  --float-reference-output build/qwen_float_replay_new/reference \
  --layer 0 --rows-start 0 --rows 16 --cols-start 0 --cols 2048 \
  --allow-zero-pad-cols --prompt "FPGA W4A8 slice validation." --token-index -1

python scripts/evaluate_qwen_quantization.py \
  --reference build/qwen_float_replay_new/reference \
  --output build/qwen_float_replay_new/evaluation
```

三个输出目录必须不存在；重复运行请换新名称，不覆盖旧证据。
`--float-reference-output`是本轮新增可选参数，不提供时原提取输出格式不变。
本轮实际提取的量化输出临时位置为`build/qwen_float_2026-10-22/requantized_replay`，
浮点参考和最终评估位置为本页第3节所列的新证据目录。

只复核已提供浮点数据时，无需Torch/模型缓存，只需Python与NumPy：

```bash
python scripts/evaluate_qwen_quantization.py \
  --reference evidence/qwen_float/2026-10-22/reference \
  --output build/qwen_float_audit_new
```

依赖仓库中原Qwen量化数据、ROM和三份UART；脚本默认同时核对旧checkpoint来源记录。
先在新证据根目录执行`sha256sum -c SHA256SUMS.txt`，再回仓库根目录运行审计。
不同NumPy版本可能改变NPY头/浮点路径；逐字节审计失败时先核查环境，不放宽整数结果比较。

## 7. 交给A的后续事项

请A先验新目录哈希，再运行评估工具，确认原浮点数据重新量化与既有交付一致。
本轮新增资料补上了此前“只能验证反量化一致性、不能评估原模型浮点误差”的缺口。
K256/K384已在B提交`44544a58`完成三次实板验证，新交接包已提供，输入与A此次包相同；
请A独立验收它们，不需要用Qwen结果替代，也不必重复上板。
确认切片误差的统计口径后，再讨论扩大样本或优化量化；本轮未修改量化算法、RTL或位流。

## 8. 本轮验证和审查

- 当前B分支的完整19阶段真实Verilator/Python回归全部通过。
- WSL Python套件69项，3项Windows专用预检跳过，其余通过；这些Windows预检已在Windows单独通过。
- Windows运行11项新增浮点参考测试和3项PDS预检，共14项全部通过。
- 测试覆盖原始浮点保存、分组参考、零参考指标、量化/ROM不匹配、错误prompt、
  错误checkpoint、错误UART标签、数据哈希缺项/篡改、输出目录覆盖/嵌套拒绝。
- 只读独立审查未发现Critical/Important问题；一个清单完整性Minor已补测试并修复。
  审查者独立核对5份NPY与3份提取源码哈希，但未独立运行数值/硬件测试；
  本轮数值重放和完整回归由B执行，不能混称为第二次独立实板验收。
- 新浮点数据通过最终脚本在独立build目录再次核验，报告与冻结评估一致。
- 原Qwen/K256/K384及旧冻结证据共256个受保护文件逐项SHA256不变，清单在`validation/protected_files.json`。

没有自动合并main，没有暂存、commit或push；代码和新证据待用户审阅后自行提交。
