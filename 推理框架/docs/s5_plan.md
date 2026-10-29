# S5 资源账本与压力测试实施计划

用户授权继续S5；沿用指定目录原地实施，不提交/推送、不修改兄弟项目或历史验收。

## 设计与决定

- 新ResourceLedger API1，支持全局/分类字节预算及分类记录数上限，原子预留/增长/释放、峰值与失败计数、确定性故障注入。
- 区分类别：arena（含对齐backing）、c_metadata（原生描述符/call/context/image）、c_profiles、trace（序列化事件字节）、task_staging（输入和输出预留）、task_records/session_records/task_events（记录数）。统一数值是受管预算，不是RSS。
- ResourceGroup通过prepare上下文接入既有C后端，不改prepare签名；第三方后端须自行接入才能宣称覆盖内部内存。Session和任务在未知/关闭未完成时保持账目，确认释放后才扣除。
- TraceRecorder可显式共享platform.ledger，失败丢事件/标记不完整；close释放内部缓存，用户此前取得的snapshot/export数据由调用方持有。
- SimDevice账本默认取显式platform或model平台，任务记录/事件设界限，staging在提交时预留，release前含终态/隔离态不提前释放；重复恢复的事件历史达到上限后计数并停止增长。
- 纯C PC allocator增加分类当前/峰值/失败统计；提供原生重复运行、预算/分配失败/未知恢复压力测试，不修改ir_core数值核心/描述格式。

## 任务

- [x] 1. ResourceLedger/ResourceGroup：先失败测试，覆盖边界、原子回滚、故障注入、GC释放和分类峰值。
- [x] 2. 接入arena/C元数据/追踪：先失败集成测试，验证prepare失败、可选profile拒绝、trace溢出、显式关闭/普通GC及未知保留。
- [x] 3. 任务/纯C资源：验证staging、记录预算、事件界限、提交失败、终态释放、拒绝恢复/确认恢复、分类原生计账。
- [x] 4. verify-resources压力验收：54样本/双链保持数值；多会话、重复任务/运行、逐点分配失败、取消/恢复/关闭重试，普通及ASan/UBSan；完整回归、一次独立审查及修复、最终指纹。

## 审查重点

预算拒绝是否在真实分配前；别名/共享权重是否重计或提前扣除；prepare/submit/close半失败是否遗留；未知资源图GC是否逃逸；观察失败是否影响数值；事件/峰值在长循环中是否真实有界。

## 执行记录

- Ruling: 受管载荷与记录数计量，不估算所有Python对象/libc开销，避免把不可靠估算当RSS；分类和未覆盖范围必须随结果披露。
- Ruling: trace可共享预算但观察失败不改数值；已经缓存的事件持续占账直到close，不因session结束虚假归零。
- Pre-flight: arena由Platform.allocate提供账本token，C prepare沿用签名用上下文接入，任务/追踪持有各自token；旧memory_info/stat键兼容保留。
- 初始3账本、4平台/后端集成、任务cap、native hook、CLI均先RED；未知device整个对象图GC导致staging0先复现，再增加强持有/恢复释放。
- 新增10专项后首次全量171/171无跳过；正式压力CLI新增至11专项，正在首轮正式验收与独立审查准备。
- Ruling: C PC服务结构扩展明确升为services ABI2、调用方须重编译；ir_core ABI/磁盘格式/函数表API1不变，不隐藏结构布局变化。
- 首轮正式24/24压力探针、54/54与双链/sanitizer通过；11项专项通过。
- 独立审查0 Critical/2 Important/0 Minor：临时原生调用表/shape数组漏账，可选profile挤占必需栈预算；两项均RED，进入一次修复，不重复独立审查。
- Final: 两项一次修复后专项13/13、全量174/174无跳过；正式24/24压力探针、2400成功任务、40故障位置与嵌套54样本/双链/sanitizer通过。
- Final: 两后端各50恢复拒绝、history限8并截断96条、两次close后归零；普通/ASan原生1000次运行和6个失败点通过；62份C分类追踪核验归零。
- Final: 原ir_core与109输入、S1—S4历史收据/证据及追踪兼容性核验后固化s5_baseline；不提交/推送。
