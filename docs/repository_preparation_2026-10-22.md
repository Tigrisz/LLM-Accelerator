# 三套板端工程的本地文件整理与提交说明

整理日期：2026-10-22。当前工作分支：`codex/b-multigroup-uart-cases`。
基准HEAD：`6c880d952ef7f54d01c94448dc0e4e1612258ced`。
本次只整理版本管理范围和文档入口，不修改RTL、PDS工程、约束、ROM或位流，不执行暂存、commit、push、fetch或merge。

## 1. 保留的三套工程

| 用途 | PDS入口 | 顶层 | 最终位流目录 |
| --- | --- | --- | --- |
| 原Qwen切片 | `fpgatest/qwen_slice/prj/prj.pds` | `fixed_slice_qwen_uart_board_top` | `fpgatest/qwen_slice/prj/generate_bitstream/` |
| A合成用例K256 | `fpgatest/a_multigroup_k256/prj/a_multigroup_k256.pds` | `a_multigroup_k256_uart_board_top` | `fpgatest/a_multigroup_k256/prj/generate_bitstream/` |
| A合成用例K384 | `fpgatest/a_multigroup_k384/prj/a_multigroup_k384.pds` | `a_multigroup_k384_uart_board_top` | `fpgatest/a_multigroup_k384/prj/generate_bitstream/` |

Qwen同时保留UART版及LED-only回退版`.sbit`。Qwen为N16、有效1536列/物理K2048，
小用例为N3/K256和N3/K384，分别每轮6条和9条部分和；不能混淆为同一模型实验。

三套工程均需保留仓库目录结构，不要只复制`.pds`。
K256/K384的`.pds`通过`../../../rtl/`引用公共模块和各自板级顶层，
约束在各`prj/source/constraints/`，初始化文件在各`prj/mem/`。
原Qwen还使用自己的`prj/source/`源码副本及根目录公共UART模块和约束，均原样保留。
工程及顶层引用的源文件、约束和三份`.mem`须随仓库一起提交。

## 2. 提交内容与本地缓存的边界

| 路径 | 处理方式 |
| --- | --- |
| `rtl/`、`model/`、`constraints/`、`scripts/`、`tests/`、`Makefile` | 保留源码、约束、数据转换/验证脚本和测试 |
| `fpgatest/`下三套工程的`.pds`、源文件、约束、`mem/`、最终`.sbit` | 保留，可纳入提交 |
| `tests/fixtures/a_multigroup/` | 保留A原始二进制/npy/仿真参考；不把simulation改称board |
| `evidence/` | 保留冻结的原始采集、JSON、清单、PDS/RTL报告和位流副本 |
| `deliveries/` | 保留原Qwen交接包、小用例交接ZIP及校验文件、A原始输入包 |
| `docs/` | 保留历史进度、验证、复现、交接资料；历史状态以各文档日期为准 |
| `build/`、`artifacts/`、`tmp/`、`.venv*/`、Python缓存 | 继续留在本机，Git忽略 |
| PDS的`compile/`、`synthesize/`、`device_map/`、`place_route/`等阶段目录 | 可重建缓存，继续留本机，Git忽略 |
| PDS的`generate_netlist/`、`report_power/`、`flow.log` | 本次补充忽略，继续留本机，不纳入新提交 |

没有删除、移动或重命名活动工程及其缓存，不需要关闭PDS。
冻结在`evidence/`中的验收报告不受PDS目录忽略规则影响。
`.gitattributes`已有规则保护`evidence/`、`deliveries/`、A夹具和`.sbit`的原始字节，
避免Windows行尾转换破坏哈希；不要手工格式化冻结证据或重新覆盖旧交接包。
如果以后重新构建/采集，应使用新的日期或新目录。

缓存未入库意味着新克隆后需要重新执行Compile至位流生成；
`.pds`中的旧完成标记和输出记录不能证明新机器已成功构建。
PDS 2022.2-SP6.4安装路径/许可证及CP2102驱动需要在新机器自行配置，不能作为源码一并提交。
ROM路径和工作目录应按工程说明设置；缺少工具时不可仅凭静态检查宣称重新综合通过。

## 3. 验证与交接资料入口

- Qwen报告：`docs/uart_board_capture_2026-10-21.md`。
- Qwen模型revision与提取命令：`docs/qwen_checkpoint_reproduction_2026-10-21.md`。
- 小用例仿真：`docs/a_multigroup_sim_validation_2026-10-21.md`。
- K256板端报告：`docs/a_multigroup_k256_board_validation_2026-10-21.md`。
- K384板端报告：`docs/a_multigroup_k384_board_validation_2026-10-21.md`。
- 小用例交接说明：`docs/task_a_multigroup_board_handoff_2026-10-22.md`。
- 小用例交接包：`deliveries/a_multigroup_board_handoff_2026-10-22.zip`及`.zip.sha256`。

原始UART、JSON和位流以相应`verification_manifest.json`及交接包校验清单为准。
本轮整理不再次下载、不重新实板复位、不更改历史验证结论。
小用例ZIP是数据/证据包，不包含完整可重新综合工程；完整工程由仓库提供。

## 4. 本次整理的核验结果

- 三套PDS工程共43条源码/约束引用全部存在，且均已跟踪或未被Git忽略；各工程三份ROM和最终位流同样在提交范围。
- 原Qwen/K256的77项保护基线全部未变；K256/K384冻结证据及工程位流与清单一致，交接ZIP哈希未变。
- `python -m unittest tests.test_capture_case tests.test_pds_batch_entry tests.test_uart_readback`：21项全部通过。
- `git diff --check`通过；暂存区无改动。Git候选文件无单个达到50MiB的文件，也没有上述PDS缓存目录。
- 这次没有重新运行PDS全流程或实板采集；仅验证整理没有破坏已保留文件和必要依赖。

## 5. 用户自行审核、暂存、提交和推送

在WSL运行：

```bash
cd /mnt/d/GPT/qiansai_FPGA
git branch --show-current
git status --short
git diff --check
git diff --stat
git ls-files --others --exclude-standard
```

Git Bash使用`cd /d/GPT/qiansai_FPGA`；PowerShell使用`Set-Location D:\GPT\qiansai_FPGA`。
确认仍在`codex/b-multigroup-uart-cases`，检查既有修改和新增文件后，再由你执行：

```bash
git add -A
git diff --cached --check
git diff --cached --stat
git diff --cached --name-only
```

应包含两套小用例工程和最终位流、测试、A夹具、板端证据、交接ZIP、文档及忽略规则；
原Qwen文件已跟踪且没有变化时，不会重复出现在差异清单中，但仍在本次提交的完整快照中。
不应新增虚拟环境、PDS构建数据库/自动网表、临时抓取目录或许可证/私钥。
已有其他修改不因本次整理自动获得正确性背书，请逐项审阅。

审核无误后由你执行（本次助手未执行）：

```bash
git commit -m "Add K256 and K384 board UART validation and handoff evidence"
git remote -v
git push -u origin codex/b-multigroup-uart-cases
```

若origin网络不可用但SSH可用，可将最后一条改为：

```bash
git push -u git@github.com:Tigrisz/LLM-Accelerator.git codex/b-multigroup-uart-cases
```

推送被拒绝时先查看远程历史并处理分歧，不使用`--force`。
推送成功后在GitHub确认分支及提交号；本地commit本身不代表已上传远程。
