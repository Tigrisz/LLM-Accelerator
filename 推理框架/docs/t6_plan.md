# T6：剩余27个FP32样本RV32迁移

用户授权：先核对软浮点及比较标准，保持原shape/storage/payload，对照Python、PC C和RV32单/双发射，覆盖重复/异常；超TCM明确阻断，不绑定模型/W4A8。

- [x] 契约：RV32IM+Zicsr/Zifencei、ILP32小端soft ABI，FP32存储/FP64计算；实际编译宏、multilib、libgcc路径/哈希/符号、链接ISA及边界执行证据。
- [x] 离线：完整54/109冻结集合，选择27 FP32；逐tensor形状/布局/原物理字节保真。遵守每例abs_plus_rel容差，拒绝非有限，单列逐位一致和padding。
- [x] 执行：一例一ELF，单/双发射；原→零→原、同步未知恢复后原、close/rebind后原。13组原契约检查；另FP32半偶舍入/次正规边界、NaN/±Inf、溢出/输出原子性/恢复探针。
- [x] 验收：TDD、一次独立只读审查、修复后的完整PC/INT32回归/FP32干净副本；旧证据完整性和新基线由封存入口逐项核验，最终状态以收据为准。

Ruling: 用户指定原地目录，复用现有工作区，不创建分支/提交/推送；不修改C核心/静态运行时、冻结输入、上游RTL、旧build证据。复用T5正向固件与T4 portable-metadata兼容RTL。代价：本轮不提供上游原始RTL/其他仿真器/实板证明。

Ruling: FP32按冻结比较标准，不将INT32逐字节参考规则当浮点容差；同一ELF单/双输出与重复同输入仍须逐字节相同，padding必须保持导出初始化的+0。数值容差通过与逐位相同分别记录；代价：仅证明既有语义和受测样本，不承诺硬件FP32 MAC或模型质量。

Pre-flight: inventory/physical/保真校验→离线准备→固件生成→UART比较共享dtype；默认INT32与旧门禁保持。新软浮点/浮点异常探针须在样本执行前完成。所有容量判定沿用真实链接诊断，不缩形。

## 执行记录

- 开始：核对C中float_result使用double展开、转换与isfinite；FLAGS禁止fast-math/FMA。现有fixture比较abs_plus_rel(atol=1e-6,rtol=1e-5)，非有限永不匹配。参考GCC官方RISC-V ABI和soft-float runtime文档，实际库/舍入以本地构建执行为准。
- 门禁TDD：新增6项先出现5 FAIL/1接口缺失ERROR，物理feed错误转换反例得到01000000而非1.5的0000c03f；实现dtype保真/容差/padding/非有限/重复确定性/符号检查后6/6通过。期间修正一处测试TensorSpec构造缺失storage_shape，不作为运行时缺陷。
- 初轮build/t6_pre_review：softfloat边界两个配置通过；异常探针在bind处失败，无trap。源码证据确认测试固件platform.recover缺失，违反现有接口必需条件；补回调，不修改运行时。旧失败与原ELF保留，下一新目录重跑。
- 修复后build/t6_pre_review_v2：27/27原FP32通过，blocked_tcm/failed/unproven/tool_error均0；54个配置执行、270份输出；边界/非有限/溢出/恢复和真实容量负控通过。观察栈1120、初始化镜像30808—31544字节，仅初验路径，不是最坏栈。父副本passed且源码前后不变。
- 冻结expected增加目标直接比较，反例先因门禁拒绝新增参考而失败，扩展后专项6/6通过；全工具初验56/56通过。能力矩阵/接入/差距/README当前口径同步，历史T5不回写。等待一次独立审查后最终回归。
- Final review: 一次独立只读审查0 Critical/1 Important/1 Minor；审查重解析54份实际日志（含直接冻结expected）、两份浮点故障日志，56工具测试通过。发现缺失证据/host异常被误标failed，以及无输出被误标单双相等。
- Final: Ruling: 原Minor的无输出相等字段按用户“未验证部分保持未知”要求提升为Important，一并修复；代价是弱证据场景的该字段由bool改为null，消费方须识别未知，不能把null当false或true。
- Final fix pass: 新增两个build_case入口级测试，编译/仿真外部边界受控，真实包/导出/门禁执行；缺mask、缺trap摘要、host exit2、双侧无输出四个反例均先FAIL。仅完整门禁之后的FP数值/padding/重复差异可用专门异常确认失败；单双等价仅两个配置完整通过后才能形成bool，确证单双差异保留false及实际输出。
- Final fix GREEN: 8/8专项通过，含真实数值越容差/同输入低位变化/两配置各自正确但字节不同仍失败；证据不足unproven、相等性null。无延期，不二次独立复审。最终PC（预计174+58）及INT32/FP32干净副本开始。
- Final: Ruling: 审查未判断的最终验收与全历史指纹由实施者实际执行；实板/原始RTL/其他版本/目标FP32多节点链/模型/完整IEEE/最坏栈ISR/时序DMA等继续未知。代价是本轮结论仅到受测单节点样本和选定RTL仿真，不能用于部署或模型质量承诺。
- Final execution: build/t6_pc_final完整174+58项无跳过、54样本、两类型四节点链×原/零、24压力/200轮、6原生含3sanitizer通过；build/t6_int32_final与build/t6_fp32_final均27/27、阻断/failed/unproven/tool_error=0。三副本各317源/数据文件、初始无build、前后源/副本不变。
- Final metrics: FP32 54个配置/270有效输出、1296个逐参考比较最大绝对误差0且逻辑逐位一致；softfloat半偶/次正规/非有限/溢出/原子性/恢复及真实容量负控通过。观察栈1120，初始化镜像30808—31544，最高BSS末32736；INT32观察栈816且27份ELF与T5指纹相同。均不是模型预算、完整最坏栈或实板结果。
- Final sealing: build/t6_finalize.py核对三个源码副本、全部新产物、原174测试/109输入/核心及T5固件/上游选择源、旧13份阶段收据及全部证据，输出build/t6_validation_final/report.json、build/t6_final_integrity.json、build/t6_baseline.json/.sha256。只本计划、验证报告与progress在运行后收尾，分列最终/受测指纹；不覆盖历史证据，不提交/推送。

## 来源

- https://gcc.gnu.org/onlinedocs/gcc/RISC-V-Options.html
- https://gcc.gnu.org/onlinedocs/gccint/Soft-float-library-routines.html
- c/src/ir_core.c、inference_ref/reference.py、oracle.py、compare.py、原fixture comparison字段。
