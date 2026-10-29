# A6 验证报告

日期 2026-10-24；规格 docs/sim_device.md，计划 docs/a6_plan.md。

最终状态：A6 完成；修复独立审查中的诊断计数问题后，90/90 项完整回归无跳过，
54/54 样本、162 比较、双类型四节点链、8 项生命周期场景和直接 C sanitizer 均通过。

## 已完成

- 协作式逻辑时钟模拟设备、有界 FIFO、单执行槽、设备注册会话和私有输入快照。
- 任务状态、输出可见性、超时、取消/确认、隔离恢复、drain/quiesce、release/关闭保护。
- 实际 A5 包/内存计划 -> A4 C 链，无 Python 数值回退。
- verify-device，54 包/双类型四节点链、8 项生命周期场景和完整报告。

## 测试先行

- A1—A5 的 71 项基线实际通过。
- 首批 A6 15 项先因缺失模拟器失败；核心完成后 14 项通过，CLI 明确因缺失入口失败。
- 补充未注册会话绕过 lease 的回归，先复现可提交，再加入注册检查后通过。
- CLI 实现后 16 项通过；进一步补充 snapshot/output weakref 释放和单个错误结果的负面对照。
- 最终完整回归、独立审查和正式验收证据在下方补充。

## 独立审查与修复

只读独立审查：Critical 0、Important 0、Minor 1。
Minor：C 已返回，但输出副本创建随后发生 MemoryError 时，原来隔离正确却丢失已完成计数。
使用真实 C 四节点链先复现 completed_steps 从应为 4 变成 0，新增回归 RED -> GREEN。
增加 A5 Session.execution_id，在异常路径仅采纳本次 run 的记录。
同时验证执行前的 MemoryError/带状态异常不借用前一次成功进度，保守隔离且不提前释放。
初始化进度和执行标识放在 run 的 try/finally 保护内；原正常同步接口和数值语义保持。

## 最终验收

| 项目 | 结果 |
| --- | --- |
| A1—A6 完整 unittest | 90/90，通过，无跳过；36.171 秒 |
| 原样本经设备任务执行 | 54/54，包括模型包加载、MemoryPlan、模拟器和实际 C 链 |
| 数值比较 | stored expected / scalar / NumPy，共 162 项通过 |
| 正常状态 | 54 个任务均 QUEUED -> TRANSFERRING -> RUNNING -> SYNCING -> SUCCEEDED |
| 四节点包 | INT32/FP32 均成功、静止、输出可见，completed_steps=4 |
| 生命周期验收场景 | 8/8，通过；每场景结束时 live_tasks=0、staging_reserved_bytes=0 |
| 等待/取消 | TIMEOUT 不终结，不释放；所有待完成阶段取消需确认；完成先到保持成功 |
| 错误/恢复 | C 后段溢出完成计数=3；数值错误可释放后重试；未知静止需恢复确认 |
| 结果门禁/租约 | 未成功可见不能读取；任务未 release 会话关闭/复用拒绝；未注册包装拒绝 |
| 额度与释放 | 任务/会话/输入+输出 staging 配额拒绝通过，release 后弱引用失效、额度归还 |
| 负面对照 | 只改错一项真实 C 结果，报告 53/54、passed=false，CLI=1 |
| 内存计划 | 全部样本实际 arena backing 等于计划；重复提交保持地址稳定 |
| 资源归零 | 54 案例主设备结束时任务、会话、staging 均 0，执行槽空闲 |
| 输入保持 | 原 109 个 fixture 文件 SHA256 不变；suite 与 A5 最终记录相同 |
| C 兼容性 | C 源码/头文件未变；ASan/UBSan 直接 C 测试退出 0，stderr 空 |
| 证据一致性 | 最终报告的全部 A6 及依赖源码哈希已与当前文件核对 |

8 项正式场景：输出可见性/输入快照、超时与取消确认、完成确认丢失与恢复、
数值错误与重试、已确认设备错误、取消确认丢失、FIFO 与 quiesce、staging 额度及陈旧句柄。
单元回归另覆盖跨设备/畸形句柄、其他线程调用拒绝、异常进度和非法配置等。

环境：WSL Ubuntu x86_64、GCC 15.2.0、Python 3.14.4、NumPy 2.3.5。
INT32 精确比较；FP32 沿用 atol=1e-6、rtol=1e-5。
测试用时只是主机测试日志，设备逻辑 tick 不等于真实时间或吞吐。

## 最终证据

- build/a6_validation_final/report.json：任务快照/事件、54 样本比较、场景、计划、哈希及工具信息。
- build/a6_validation_final/packages/：54 个实际加载的模型包，不含 expected 值。
- build/a6_validation_final/chains/：两个四节点静态合成包。
- build/a6_validation_final/backend/：实际 C 动态库、build.json 和编译日志。
- build/a6_validation_final/native_tests/：直接 C ASan/UBSan 可执行文件、命令、日志与 result.json。
- build/a6_unittest_final.log：90 项完整回归日志。

重新执行使用 sim_device.md 命令，换一个不存在的输出目录以保留既有验收记录。
A7 完整运行时追踪仍未实现。

## 边界

PC 逻辑事件模拟，不创建执行工作线程；一个同步 C 链在单次模拟事件中执行，不支持中途抢占。
输入传输/输出可见性为协议阶段，不是实际 DMA/cache 同步。
无真实模型、W4A8、RV32/FPGA/驱动或性能验收。原生 ASan/UBSan 对象是直接 C 核心测试。
所有设备资源保护结论以模拟状态/所有者线程契约为范围；实际硬件静止确认须由驱动实现。
不改原 54 样本，不提交、不推送，不改其他项目。
