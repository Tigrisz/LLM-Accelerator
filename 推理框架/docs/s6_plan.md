# S6 候选模型接入准备计划

用户授权：整理算子、dtype、量化、布局与内存需求，形成接入清单和当前能力差距；不选定模型或W4A8。
指定目录原地实施，不提交/推送，不改运行时代码、ABI、冻结输入或历史证据。

## 交付与决定

- docs/model_intake.md：采集流程、检查清单、证据与准入状态。
- templates/candidate_requirements_v1.json：未填写的候选需求；null明确为未知，不当作不需要/通过。
- templates/operator_requirement_v1.json、tensor_requirement_v1.json、quantization_requirement_v1.json：逐项采集字段。
- docs/capability_matrix.md：以当前源码/实际后端/验证证据为准的能力矩阵。
- docs/model_gap_analysis.md：阻断差距、条件转换和验证缺口，不实施新算子/模型导入器。
- docs/model_memory_requirements.md：arena/C元数据/追踪/任务/可选持久缓存的口径与预算公式。
- build/s6_validation_final：可复现只读审计脚本、实际54样本/双链的能力查询与规划、缺口负控、模板与文档完整性、源码/历史证据指纹。

## 任务

- [x] 1. 核对S5实际支持集、数量/大小边界、数值/资源限制；整理模型无关模板。
- [x] 2. 清单/矩阵/差距/内存说明，关联需求ID、源码和验收证据。
- [x] 3. 使用现有54样本及两条四节点链验证两后端查询/内存估算/真实C输出；明确拒绝新算子、量化/布局/dtype/动态或批量语义。
- [x] 4. 一次独立只读审查，修正文档/审计结论，核验历史与当前指纹，形成验收说明和S6收据。

## 执行记录

- Ruling: S6是接入准备与证据整理，不新增runtime支持或自动接入判断产品接口；工具继续0.5.0，文档资料/模板独立v1。
- Ruling: 无候选模型时不填造模型指标、quant格式、上下文长度或板端预算；null/unassessed保持待补，不能给整体可接入结论。
- Ruling: 检查优先按实际候选关键路径和目标资源排序，不把Transformer/生成/KV或某量化方式设为所有模型的必需条件。
- 首轮54/54、108样本query、324样本参考比较与双类型四节点链通过；28类query拒绝和7项包/预算/地址负控通过，4模板保持pending。
- 独立只读审查0 Critical/1 Important/2 Minor；padding字节零描述误判、转换状态条件矛盾、query先于plan的流程顺序。
- Final Ruling: 后两项虽原判Minor，但直接影响清单准入状态和流程可执行性，按本轮文档验收影响升级Important，同一批修正；原severity保留在验收收据。
- 一次修复：区分数值零与writer默认字节，统一无实现/证据为pending_validation，改为read→plan→query→bind；追加实际FP32负零padding正控与非零padding负控，不独立复审。
- Final: 最终54/54、108样本query、324样本比较、双链与负零补充18比较通过；28类两后端query负控、8包/预算/地址负控、4模板通过，资源归零。
- Final: 55源码/测试、109冻结输入不变；S1—S5历史收据/证据核验。完整174项与sanitizer未本轮重跑，明确为S5历史记录；本轮无运行时代码变更。
- S6: complete，文档/模板v1；无候选时仍pending，不预设模型/W4A8，不提交/推送。
