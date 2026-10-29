# S6 接入准备验证报告

2026-10-25；资料/模板v1，运行时保持0.5.0。S6是需求整理、差距分析与证据核验，不新增执行支持。

## 交付

- model_intake.md：19项SRC/EXE/OP/DT/Q/LAY/MEM/PKG/VAL/HW接入检查及状态/证据/退出条件。
- ../templates/下4份JSON：候选总表、逐算子、逐张量、量化需求；未定字段为null，整体pending。
- capability_matrix.md：当前支持集、数值/布局/包大小/资源/后端/部署与ABI边界及源码依据。
- model_gap_analysis.md：10类条件差距、依赖、后续验收与转换证据要求，不预设架构/量化方案。
- model_memory_requirements.md：每profile内存采集、共享/并发/prepare峰值、量化/可选状态的条件公式与系统额外开销。

## 本轮实际验证

在WSL Ubuntu x86_64、Python3.14.4/NumPy2.3.5上，使用S5已验收且SHA256相符的C共享库执行；
源代码与库侧元数据匹配，没有重编译或修改运行时代码。

- **54/54**现有样本，通过两后端**108次样本query、324次样本参考比较**（stored/标量Python/独立NumPy各一份）。
  两后端输出逐字节一致。此处参考计算只用于验证，没有在C执行失败后回退重跑。
- INT32/FP32两条四节点链均经两后端query/真实C执行，与手算/标量/NumPy一致，另12次比较。
- **28类缺口×两后端**均明确不支持：新算子、未实现dtype、strided/rank0/rank5/动态或空维、
  元素上限、设备域、属性/量化字段、只读输出、scratch/对齐不足、batch linear和broadcast add。
  这是合成能力探针，不是候选模型分析；query正例仍不代替包/图/数值/资源检查。
- **8项包/预算/地址负控**拒绝：包中未实现量化/状态字段、node/tensor/源权重越限、
  arena预算低于需求、32位4GiB长度、数值非零物理padding；精确arena预算和0xffffffff最后字节数学检查接受。
- 新增FP32负零padding正控：常量padding具有非零位模式（小端00000080），严格包校验及两C后端均接受；
  与原参考一致，另6次比较。证明“数值零”不能误写为加载器“只准零字节”。
- 54样本及双链的原C/S4元数据公式分别与S5实际账目一致。
  四节点链示例：W=256、activation=128、workspace=64、含对齐arena方案637字节；
  本机不启用profile时原C元数据1092、静态C适配元数据22785字节。
  这些是合成链/x86_64示例，不是候选模型/RV32大小，也未包含全RSS。
- **4/4模板**为有效JSON且unassessed/pending；模型ID、算子清单、量化清单、目标内存均保持未知。
- **55份runtime/C/tests文件、109份冻结输入**本轮指纹不变；S1—S5收据自校验及历史验收文件指纹全部核对通过。
- 实际执行结束，平台live_allocations/backing/open_sources/retained_resources和S5 ledger live_bytes/live_entries均0。

样本比较324次，链及负零正控另18次；它们不构成实际模型应用质量或板端验证。
本轮未重复运行S5的174项全量单元测试或ASan/UBSan；其历史证据指纹已复核，不能当成本轮新执行结果。
文档/模板变更采用上述实际能力/数值/布局/预算审计验证，没有增加镜像实现的单元测试。

## 独立审查与修正

一次只读独立审查原判：0 Critical、1 Important、2 Minor。

1. Important：矩阵/内存文档误把数值零padding写成零字节准入；审查定向探针确认FP32负零可接受。
2. Minor：差距文档允许无实现/证据的转换进入conditional_conversion，与主清单矛盾。
3. Minor：主清单query写在plan之前，无法按现有requirements_for(package,plan)直接执行。

本轮以清单准入与流程可执行性为验收目标，作者将后两项升级Important，同批修正三项。
最终文档区分writer默认初始化与数值检查；无实现或证据统一pending_validation；流程改为read→plan→query→bind。
实际负零正控/非零负控与全审计复验通过；没有第二轮独立复审。

## 复现与限制

最终报告build/s6_validation_final/report.json，逐包inspection.json和可复现审计脚本同目录；
初审资料保留在build/s6_validation_pre_review。最终收据build/s6_baseline.json和.sha256。

审计不覆盖既有目录；在当前S5源码/库指纹一致的WSL目录中，复制到新build子目录执行：

```text
mkdir build/s6_rerun
cp build/s6_validation_final/audit.py build/s6_rerun/audit.py
python3 -B build/s6_rerun/audit.py
```

后续若运行时已演进，脚本会因S5源码指纹变化拒绝复验；应重新核对能力并创建新的基线，不应忽略该检查。

没有指定/下载候选模型，没有真实operator inventory、量化参数、应用质量或目标内存/性能测量；
候选结论严格为pending。只有linear/add/relu、FP32/原始INT32、连续行优先等既有子集可执行；
本轮不实现新算子、量化/状态协议、外部格式转换或板端驱动，不绑定W4A8。
未提交/推送，原C/Python/tests/冻结输入及S1—S5历史证据保持不变。
