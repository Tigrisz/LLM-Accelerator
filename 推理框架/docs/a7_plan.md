# A7 运行时追踪实施计划

2026-10-24；依据用户明确授权继续 A7，及 A1—A6 已确认架构。
采用 writing-plans / executing-plans / test-driven-development，最终独立只读审查。
Ruling：指定目录原地实施，不提交/推送、不另设审批；不改 frozen fixtures 或其他项目。

## 规格

完整覆盖当前静态 PC 运行时：模型加载/来源、计划与张量/节点元数据、会话创建/关闭、
输入检查/准备、实际 C 链及逐节点结果、输出复制、设备任务接受/拒绝/状态、
等待/超时/取消/隔离/恢复/读取/释放。不是完整模型生成、板端驱动或硬件分析器。
同一 recorder 关联 trace/model/session/run/device/task 标识；记录元数据，不保存权重/输入输出值。

Ruling：C 新增可选 profiled chain API，原 ABI/普通 chain 保持兼容；共享链校验与执行实现，
记录真实已执行/失败/跳过节点、C clock() process CPU tick，缺失或回绕标无效。
主机阶段用 perf_counter_ns；设备逻辑 tick 单列。三种时钟绝不相加或冒充 FPGA 时延。

有界 TraceRecorder，默认 16384 事件、16MiB JSON 事件预算；溢出/观察错误计数并 complete=false。
常规追踪错误不改变数值、任务终态或 lease；无 C profiling 能力时仍执行普通 C，追踪标不完整。
JSON + Chrome/Perfetto-compatible Trace Event JSON + summary JSON 独占导出到新目录；
拒绝覆盖。摘要含逐算子 CPU 统计、主机阶段、任务/错误、计划内存和已观察会话 backing，
明确不等于进程 RSS 或硬件性能。保留 A6 原 events/生命周期行为。

## 文件与接口

- c/include/ir_core.h、c/src/ir_core.c：ir_node_profile、ir_execute_chain_profiled、时钟/结构信息；
  profile 输出区校验包含调用数组、计数器、描述符、张量和工作区别名，执行前拒绝。
- inference_ref/c_backend.py：可选 profile ABI 绑定；旧库仍可正常无追踪执行。
- inference_ref/tracing.py：TraceRecorder、safe record/context、调用观测、导出/摘要/完整性校验。
- runtime.py：load_model/create_session(trace=...)；模型/计划事件、主机阶段、C 节点与 run 关联。
- sim_device.py：SimDevice(trace=...)；任务状态/资源和 API 调用观测，与内部 C 执行关联。
- trace_validation.py、__main__.py：verify-trace，54 样本追踪开/关对照、162参考比较、
  逐节点链、错误/超时/恢复、丢失观测及负面对照，导出并回读验证。
- tests/test_tracing.py、c/tests/test_core.c；docs/tracing.md、a7_validation_report.md。

## 任务与验收

- [x] 1. recorder/导出：测试先失败再实现，顺序/关联/不可变快照/预算/损坏和覆盖拒绝。
- [x] 2. C 观测：直接 C 测试先 RED；真实四节点/失败/跳过/别名，普通路径不变，ASan/UBSan。
- [x] 3. A5/A6 接入：先端到端 RED；追踪开关数值一致、重试/取消/超时/隔离/释放不改变；
  主机、CPU、逻辑时钟明确标记，收集错误不改变任务执行。
- [x] 4. 54 样本/双类型四节点/生命周期完整验收、导出回读、负面对照、完整旧新回归、
  独立审查与最终复验，记录源码/构建/样本哈希。

Pre-flight：profile buffer 独立于 runtime arenas，追踪额外内存不计入 A5 arena 预算；
模型/计划记录一次，run/task 关联实际执行代次，状态观测失败不能打断 A6 lease 更新。
Review focus：C profile 别名/容量与失败原子性、异常与旧进度串联、追踪溢出/错误对执行影响、
时间域混用、导出完整性/错误成功判定、重复模型/会话及资源引用保留。
台账 docs/progress.md；最终证据新 build/a7_* 目录。
