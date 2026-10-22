# Qwen浮点参考与量化误差评估：提交整理说明

整理日期：2026-10-22。工作分支：`codex/b-multigroup-uart-cases`。
整理时HEAD为`44544a58ad65a4bb383608a9f403b12b82d70376`。
本轮只整理新增资料和入口，不改计算功能，不覆盖原Qwen/K256/K384工程、ROM、位流或验证资料。
没有执行git add、commit、push、merge、rebase或再次获取远程。

## 本轮提交清单

| 路径 | 内容 |
| --- | --- |
| `scripts/extract_qwen_slice.py` | 新增可选浮点参考输出，旧默认提取流程保持兼容 |
| `model/float_reference.py` | 保存W4A8量化前的权重、激活，生成FP64/FP32参考和来源清单 |
| `scripts/evaluate_qwen_quantization.py` | 重新量化/ROM/UART一致性核验和误差计算 |
| `tests/test_qwen_float_reference.py` | 11项新增测试，含篡改、缺项、错误标签/来源和输出覆盖拒绝 |
| `evidence/qwen_float/2026-10-22/` | 46份冻结文件：原浮点参考、误差结果、重建量化输入/ROM、19阶段回归日志、来源/保护记录、SHA256清单 |
| `docs/qwen_float_reference_2026-10-22.md` | 详细结果、固定checkpoint复现命令及适用边界 |
| `docs/task_a_qwen_float_handoff_2026-10-22.md` | A侧包内哈希及数值重算步骤 |
| `docs/repository_preparation_qwen_float_2026-10-22.md` | 本提交清单 |
| `deliveries/qwen_float_handoff_2026-10-22.zip`及`.zip.sha256` | 已冻结并解压验证的数据/核验工具交接包 |
| `README.md`、`.gitattributes` | 文档入口和提取/评估核心文件的LF行尾规则 |

`model/model_slice.py`内容没有修改；只为它及本轮4份提取/评估/测试源码显式设置LF行尾，
避免core.autocrlf=true时重新检出改变已记录的核心源码字节哈希。
不是对整个仓库或历史报告做行尾重写，不执行git add --renormalize。
已有`evidence/**`、`deliveries/**`和`.sbit`禁用文本转换的规则继续生效。

原三套工程和旧验证资料已经随此前提交保留，不应重复挪动、重命名或删除。
原Qwen对应UART位流以及LED-only回退位流、K256/K384各自位流全部保留。
原三套工程及旧资料的保护记录为新证据中`validation/protected_files.json`，256项哈希不变。

## 哪些文件继续仅保留在本机

- `build/qwen_float_*`：提取重放和审计临时输出，可重建。
- `artifacts/deliveries/qwen_float_*`及`verify_qwen_float_*`：打包暂存、解压验证和临时审计目录。
- `artifacts/qwen_float/2026-10-22/`：过程保护快照、初步报告。
- `.venv*/`、`__pycache__/`、`tmp/`、PDS缓存：沿用现有忽略规则。

这些文件没有删除，只是不进入Git；必要冻结结果已在`evidence/`和`deliveries/`中。
不提交HF checkpoint缓存、许可证、私钥或完整虚拟环境。
本轮无需新增.gitignore规则，也不移除旧已跟踪文件。

## 结果与证据边界

固定revision：`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`，
Qwen2.5-1.5B-Instruct layer0 o_proj，N16、有效1536列/物理K2048，同一prompt和最后token。
原始BF16权重/激活在W4A8量化前转FP32保存，不是FP32模型重新推理或反量化伪造原值。
重新量化5份载荷、3份ROM及三次旧UART对应关系通过；最大绝对误差0.07159525、
RMSE0.03205081、相对L2约9.71%、最大逐行相对误差约63.79%。没有约定模型精度验收阈值。

此前已执行19阶段完整回归，WSL套件69项（3项Windows专用预检跳过），
Windows单独14项通过；打包后另在解压目录验证11项新增测试和数值重算。
本轮整理只复查文件完整性和相关测试，不冒称重新运行PDS或物理上板。

交接ZIP校验值：

```text
65d7bf5fee9fe0578b761ceba35e7f6bd1e070117ed4f20a4c9315a66d16f310
```

ZIP含当时脚本、证据和核验README，不含完整可重新综合的RTL/PDS工程。
本轮提交整理文档与仓库属性属于仓库管理，不回写已冻结ZIP，故ZIP哈希不变。

## 用户自行审核、提交和推送

WSL在仓库根目录执行；Git Bash可先`cd /d/GPT/qiansai_FPGA`：

```bash
cd /mnt/d/GPT/qiansai_FPGA
git branch --show-current
git status --short
git diff --check
git diff --stat
git ls-files --others --exclude-standard
```

PowerShell可先`Set-Location D:\GPT\qiansai_FPGA`，其余Git命令相同。
确认当前分支和清单无误后，你可以只暂存本轮文件：

```bash
git add .gitattributes README.md scripts/extract_qwen_slice.py model/float_reference.py scripts/evaluate_qwen_quantization.py tests/test_qwen_float_reference.py docs/qwen_float_reference_2026-10-22.md docs/task_a_qwen_float_handoff_2026-10-22.md docs/repository_preparation_qwen_float_2026-10-22.md evidence/qwen_float/2026-10-22 deliveries/qwen_float_handoff_2026-10-22.zip deliveries/qwen_float_handoff_2026-10-22.zip.sha256
git diff --cached --check
git diff --cached --stat
git diff --cached --name-only
```

检查没有新增build/artifacts/虚拟环境/PDS缓存，也没有删除原工程、位流和旧证据。
确认后再由你执行：

```bash
git commit -m "Add original Qwen float reference and quantization error evidence"
git push origin codex/b-multigroup-uart-cases
```

若origin的HTTPS不可用而SSH可用，可改为：

```bash
git push git@github.com:Tigrisz/LLM-Accelerator.git codex/b-multigroup-uart-cases
```

已有upstream，无需重新设置；这不会自动合并main。
只有先commit才会推送新增浮点工作；推送成功后记录新提交号，不能继续用旧`44544a58`冒充浮点交付版本。
之前获取的main为`29211823`，本轮未合并。需要集成A更新时，应另外检查最新远程历史及冲突并重新验证，
不要为了上传资料直接强推或覆盖main。
