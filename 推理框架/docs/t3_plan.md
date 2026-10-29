# T3 纯 C 元数据与栈优化计划

用户授权在指定目录原地执行；不绑定模型/W4A8，先PC回归，目标工具链/布局/栈峰值仍未知。使用计划、测试先行、内联执行与完成前验证技能；末尾一次独立只读审查。

## 规格与决定

- 磁盘IRS4BIN1、ir_core ABI1、平台/后端函数表API1、PC services ABI2保持；纯C运行时结构/调用ABI升为2，使用irs_inspect_v2/irs_bind_v2导出名，旧二进制不混用，调用方重编译迁移。
- 保留4096 tensors/1024 nodes上限，调用方可提供更小的实际容量；不足拒绝，不截断。int16生命周期[-2,1024]，每tensor4字节检查工作区；不改数值路径/算法复杂度。
- context移除roles/supplied固定数组，改为指向调用方每tensor1字节状态（角色2bit、输入已供应1bit）。状态持有到成功close；检查工作区仅inspect/bind期间借用，成功/失败确认返回后可复用/释放。
- 新header读取/尺寸查询用于分配，不代表图语义验证；完整inspect仍验证CRC、图序、生命周期及arena别名。查询/检查out及scratch不得与图像重叠；bind全部元数据/状态/检查区/arena/服务结构必须先查边界与别名后写。
- 容量工作区、PC账本与ctypes适配同步；bind临时工作区计c_metadata实际分配而非伪装stack，profile可选分配不能挤掉必需工作区；run不分配。
- T2资料保留历史含义：9份当时框架源固定快照、来源索引指向快照，旧T2收据/build证据不改；T3当前结果另列，不把历史32KiB/20KiB当当前实现。

## 任务与验收

- [x] 1. 新C专项/工具测试先RED：容量/边界/别名、并行独立context、scratch释放后run、异常保留恢复、最大张量/节点、旧ABI拒绝。
- [x] 2. 实现ABI2查询/inspect/bind/state，迁移host/native tests/Python绑定与分类账目，保留原174测试源和原C数值核心/109输入。
- [x] 3. PC sizeof、GCC .su按相同flags对比T2；不以静态frame之和冒充实测栈峰值。专项普通/sanitizer/预算失败和多次运行通过。
- [x] 4. 无历史build副本运行原174＋全部工具测试、54样本/双链/24项200轮压力与S6/T2来源审计；一次独立审查，必要修复后最终新副本验收。
- [x] 5. 文档版本/兼容性/资源公式及未知项统一，固化本轮源码/证据指纹。

## Review Focus

1. caller工作区/状态与image/ctx/arena/服务/out别名或不足容量时，必须先拒绝，不破坏既有调用方对象。
2. scratch是临时、state是常驻；未知执行不得提前释放state/arena，两个context不得共享状态。
3. 最大上限、未使用/重复/前向张量、闭生命周期重叠与节点内alias语义保持，压缩int16不溢出。
4. 不隐藏heap/全局scratch；可选profile不能先占用必需资源；失败后回滚、close重试/恢复资源归零。
5. T2历史来源与当前T3事实区分，旧库必须在ctypes改变调用签名前拒绝；不宣布目标sizeof/布局/栈峰值已验证。

## 执行记录

- Ruling: 用户已给出实施范围，按本计划连续执行，不另建worktree/提交/推送，不更改兄弟项目；ABI2不兼容属于明确迁移成本。
- Ruling: 保留磁盘上限，采用caller-owned动态大小元数据，避免靠缩小全局固定上限或重复扫描图来换栈；代价为调用方新增两个缓冲的显式生命周期。
- 初始3项T3 RED→GREEN；新增最大实际整链、free工作区后run、账本边界、nm和PC sizeof/frame比较，工具26/26通过；原174/174无跳过。
- 第一轮新副本原174/工具26/54样本/双链/24项200轮压力通过；S6公式漏计新增T字节state导致整体失败，保留失败证据，补齐工具/文档公式后单独复验，再最终重建。
- S6复验54/324比较/28查询类/8其他负控通过；GCC15.2 PC sizeof20672→200，inspect frame32928→192，bind448→480；目标sizeof/栈峰值保持unknown。
- 2026-10-26续作：唯一一次独立只读审查0 Critical/1 Important/1 Minor，前轮自动审批因用量限额未执行的文档更新已在本轮完成，无绕过审批。
- Final Ruling: 用户明确要求同时处理两项；将原Minor的容量文档冲突按契约重要性同批闭合。arena保持原整段互斥，元数据用必需前缀；代价是arena未使用尾部也不能与其他区共享。
- host profile预算/分配失败四种normal/sanitizer组合先RED（status4中止），改为继续计算但观测不完整后GREEN；arena尾部负控确认保守行为不变；全部工具27/27无跳过，build/t3_tools_review_fix。
- 不进行第二轮独立复审；原审查未判断的目标工具/布局/栈峰值/实板保持unknown，最终新干净副本由本执行者复验。
- T3 complete（PC范围）。2026-10-26最终build/t3_final顶层passed/exit0；原174+工具27均无跳过，54样本/双链/24项200轮压力/普通与sanitizer/S6/T2/PC元数据审计全部通过。
- 完成时源/副本274文件一致，产物1116指纹；之后仅plan/report/progress收尾，代码和输入不变。收据build/t3_baseline.json/.sha256，汇总t3_validation_final/report.json与t3_final_integrity.json。
- 原174测试源、109输入、ir_core三件套、T2九份固定源和S1—T2历史收据/证据核验；不提交/推送。
