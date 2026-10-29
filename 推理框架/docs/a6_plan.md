# A6 模拟设备与任务生命周期实施计划

日期 2026-10-24；依据用户明确续做 A6 的授权及 contracts.md 已批准设备契约。
执行 writing-plans / executing-plans / test-driven-development，最后独立只读审查。

## 规格与选择

采用单所有者线程、显式逻辑 tick 的协作式设备模拟器；有界 FIFO、单执行槽、
每会话最多一个未 release 任务。实际计算调用 A5 Session.run -> A4 ir_execute_chain。
不创建后台线程，不把逻辑时间解释为真实耗时；不模拟真实 MMIO/DMA/cache coherence。
Ruling：直接落实已确认路线，不另设审批；在用户指定目录原地实施，不提交/推送。
Ruling：逻辑事件模拟替代工作线程，保证超时/取消/确认丢失能确定性复现；
代价是本轮不验证真正并发或计算进行中的硬件抢占。

状态 QUEUED -> TRANSFERRING -> RUNNING -> SYNCING -> SUCCEEDED；
数值/已确认设备错误 -> FAILED；取消先 CANCEL_REQUESTED，确认后 CANCELLED；
无法确认静止 -> QUARANTINED，经 recover -> RECOVERING，模拟器确认后 FAILED。
终态只有 SUCCEEDED / FAILED / CANCELLED，且必须 quiescent=true。
WAIT TIMEOUT 是等待结果，不能改成终态；poll 不推进时钟。
提交前严格校验，成功提交后私有复制输入，持有会话 arena 的 lease；
输入和预留输出副本计入独立 staging 预算，按任务数/会话数限制资源。
只有 SUCCEEDED 且确认可见才能 result；只在终态静止后 release，之后句柄过期。
release 前，复用/关闭会话和关闭设备都拒绝；结果返回独立副本。
quiesce 发起取消并等待确认，不能用 wait 超时或调用方布尔量冒充设备静止。
注入 device_error / lost_completion / stuck_cancel，不接受任意可执行回调。

## 文件及接口

- inference_ref/sim_device.py：SimConfig、TaskHandle/Snapshot/Event、WaitResult/DrainResult，
  SimDevice.query_support/create_session/submit/poll/wait/cancel/result/release/advance/recover/drain/quiesce/close。
- inference_ref/runtime.py：提取无副作用 validate_feeds，供 A5/A6 共用；同步行为保持。
- inference_ref/device_validation.py：54 个模型包 -> 模拟任务 -> C 的 162 比较、生命周期场景和报告。
- __main__.py：verify-device；原 CLI 保持兼容。
- tests/test_sim_device.py：先观察缺失实现失败，再验证状态、保护、错误、配额、句柄、重复运行。
- docs/sim_device.md、a6_validation_report.md，更新 README/contracts/progress。

## 任务与验收

- [x] 1. 状态/所有权：测试先行；输入快照、结果门禁、busy/释放、FIFO、取消确认及超时无终态。
- [x] 2. 错误/恢复：设备故障、C 数值错误、确认丢失/取消失联隔离，恢复确认后才能释放。
- [x] 3. 集成/验收：所有原 54 样本经 A5 包与计划、模拟器和真实 C 执行，162 比较通过；
  双类型四节点包、重复运行、生命周期场景可复查。CLI 失败不冒报通过。
- [x] 4. 完整 A1—A6 回归、直接 C ASan/UBSan、输入/源码/二进制哈希、独立审查、最终复验。

Pre-flight：validate_feeds 无副作用；SimSession 独占内层 A5 Session，不暴露可变 arena；
任务 lease 跨等待、取消和隔离保留，直到 release。现有 plan/包格式/C ABI 均不改变。
Review focus：取消/完成竞争、陈旧及跨设备句柄、确认丢失与超时后资源释放、
拒绝提交的副作用、资源限制及意外执行异常。执行台账 docs/progress.md。

最终：90/90 项无跳过，54/54 样本与 162 比较、两条四节点链、8 项生命周期场景通过。
独立审查 0 Critical / 0 Important / 1 Minor；意外异常已完成计数丢失经 RED -> GREEN 修复，
并验证不会串入前一次执行进度。A4 C 核心和原 fixtures 保持不变。
证据 build/a6_validation_final/report.json、build/a6_unittest_final.log。
