# S6 候选模型接入检查清单 v1

当前运行时工具0.6.0（T3，native ABI2）；S6提供接入资料与核验，不扩展执行能力、不选择具体模型或量化方式。
T4指定INT32链、T5/T6原单节点样本、T7原FP32/INT32四节点链（含部分失败恢复）的RV32结果分别见各期验证报告。引用时逐项标PC、RTL仿真或实板；不能据受测链将候选标为target_validated，任意FP32图/模型、实板、完整最坏栈仍未验证。
先读capability_matrix.md、model_gap_analysis.md、model_memory_requirements.md。
空白模板在../templates/；这是本地需求采集格式，不是可执行model-package-v1，也不是ONNX等格式转换器。

## 使用与决策

每个候选、每个固定形状/阶段profile独立采集，并固定来源版本、文件哈希和参考输出。
复制candidate_requirements_v1.json并填写；operator/tensor/quantization模板按实际条目复制，
把其文件路径/条目ID填写到inventory中。不能直接把需求模板交给load_model/export_static。

- `null`：未知；`false`：经证据确认不需要；`[]`：经确认没有条目。三者不能互换。
- 所有关键字段先保持unassessed/pending。填完名称、dtype或通过一条query均不表示模型已接入。
- 有证据的逐项状态：supported（当前子集匹配）、unsupported（当前明确不支持）、
  conditional_conversion（需要明确转换和等价性验证）、pending_information（材料待补）、
  pending_validation（实现或平台尚无目标验证）。不能把pending当supported或mismatch。
- overall_decision：pending / blocked_information / blocked_capability / ready_for_pc_trial / pc_validated / target_validated。
  本轮所有空模板为pending；没有候选模型证据，不给pc_validated/target_validated结论。
- ready_for_pc_trial仅表示准入材料和当前能力检查齐备，可进入试验；pc_validated还需实际模型数值/质量/资源验收；
  target_validated还需目标机工具链、内存图、同步、性能和异常恢复证据。
- 新算子/量化/状态/后端是阻断项；只有显式转换方案、数值证据与实际执行路径齐备才允许转为conditional_conversion。
  不能仅把“可反量化/可拆分/可离线转置”写成已经支持。

## 接入检查清单

每行记录“状态、来源/证据路径与SHA256、问题、负责人、下一步和验收条件”；未勾选不自动等于不支持。

| ID | 必须查清的内容 | 本阶段验收证据 |
|---|---|---|
| SRC-01 | 模型任务、来源URI/revision、文件清单/哈希、许可与导出版本 | 固定来源和可重复导出记录；不只给模型名称 |
| SRC-02 | 预处理/后处理、输入输出含义；tokenizer或词表是否实际需要 | 最小输入→参考输出可复现；无此功能时明确false及依据 |
| EXE-01 | 静态/动态、batch、输入尺寸/长度/阶段profile、最大并发/会话数 | 实际profile表；当前仅正整数固定形状，不把一组范围当已支持动态执行 |
| EXE-02 | 是否有持久状态、更新/reset、取消和恢复语义 | 状态字段/容量/生命周期；静态Session.run不能替代生成或流式状态协议 |
| OP-01 | 全图逐节点名称/命名空间/版本、次数、连接、所有输出 | 完整operator_inventory；不能只统计主计算算子 |
| OP-02 | axes、transpose、broadcast、fusion、mask、epsilon、归约等精确属性 | 每节点语义和输入角色；对照当前linear/add/relu支持边界 |
| OP-03 | 现有后端整链query、实际选中后端和显式回退策略 | 每节点SupportReport与实际run来源；query支持不证明数值和目标性能 |
| DT-01 | 每个输入/权重/bias/计算/累加/输出dtype；混合精度与溢出 | 数值方程与舍入/饱和规则；INT32原始整数不代表量化计算 |
| Q-01 | 是否量化、编码版本、位宽/符号、packing/位序、尾组、scale/zero point布局 | 完整quantization_requirement；未知保持null；不默认分组大小/轴/位宽 |
| Q-02 | 反量化/重量化、校准来源、输出转换、量化质量门槛 | 独立参考、边界值和端到端质量结果；不能用小样本容差替代模型精度 |
| LAY-01 | 逻辑轴/形状、物理轴/形状、stride、连续性、tiling与padding编码 | tensor_inventory；当前仅连续row_major、rank1..4和零padding |
| LAY-02 | 源权重方向、端序、对齐、alias/in-place、读写权限与内存域 | 导出/转换记录和物理字节核对；不允许静默转置或跨域指针混用 |
| MEM-01 | 原文件、运行权重、激活峰值、工作区、持久状态、元数据、栈、追踪、任务 | 每profile的容量/并发公式与实测峰值；区分源字节、逻辑/物理/保留字节 |
| MEM-02 | 实际目标可用内存/地址图、32位范围、DMA可达区、对齐与预算 | 目标资源表与预留余量；64MiB默认PC预算不是板上可用内存 |
| MEM-03 | 分配失败、并发、终态未release、拒绝恢复、close重试的峰值和归零 | S5同口径资源报告；RSS/加载器/调用方副本额外测量，不能漏算 |
| PKG-01 | 是否已有到自有包v1的可证明映射；数量/大小/版本/校验和 | PC严格read_package、plan、地址检查、export_static与C bind证据 |
| VAL-01 | 逐算子与整图golden、dtype/布局/尾部/极值、数值阈值 | 标量/独立参考和C输出；原54样本只证明基础子集，不能冒充真实模型测试 |
| VAL-02 | 应用质量、资源、时延/吞吐/功耗目标及测量条件 | 候选实际输入集与运行日志；未知目标指标不填达标 |
| HW-01 | 目标编译器/ABI/端序、驱动、地址映射、搬运/同步/恢复 | 编译/运行/故障/trace证据；PC host-coherent不证明DMA/cache/FENCE |

## 执行顺序和退出条件

1. 收集SRC/EXE材料；信息缺失先阻断结论，仍可独立测量已知张量/算子。
2. 填逐节点/张量/量化表；对照能力矩阵给出每条差距与条件转换，禁止静默改语义。
3. 为每个固定profile核算内存和目标上限；未知量明确列出，不能用参数量直接判断可运行。
4. 当前子集匹配时，PC转换到自有包→严格read_package→plan_memory与地址检查→构造requirements并query→C绑定→逐层/整图比较→S5故障/压力。
5. 候选质量/资源达标后再做目标机试验；新增能力单独形成实现方案、参考和验收，不在S6假定已完成。

当前无需模型即可完成：模板/矩阵、现有子集回归、目标资源采集表、导出/数值/内存验收流程。
必须等候选材料：真实operator inventory、量化方程、profile/状态维度、权重与应用质量结果。
必须等目标材料：可用内存图、设备接口/同步和目标性能。上述待补不是本轮整理失败，也不意味着模型不兼容。
# T8当前验收说明

既有54样本与两条四节点链由[t8_validation_report.md](t8_validation_report.md)所述统一入口验收；不扩大模型准入支持，也不能代替候选模型golden、完整内存及实板验收。

