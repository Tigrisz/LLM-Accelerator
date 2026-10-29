# A7 验证报告

2026-10-24；范围见 tracing.md，计划 a7_plan.md。

## 已实现

- 有界 TraceRecorder，元数据关联、三种时钟分离、JSON/时间线/统计及哈希导出回读。
- C 可选逐节点 profile ABI，与原链共享校验/计算；别名/容量执行前拒绝。
- 模型/内存计划/会话/run 与模拟任务接入，主机阶段的失败也记录状态。
- verify-trace：54 样本开关逐字节对照、162 比较、双类型链、8 场景和观察失败探针。

## 测试先行

- A1—A6 原 90 项基线通过。
- 初始 A7 9 项因缺失追踪实现失败；直接 C 测试因缺失观测类型/API 编译失败。
- 录制器先通过 3 项；C 观测直接测试及 ASan/UBSan 通过；再接入 runtime/device。
- 伪造 session 关联、None events 文档、CPU 时钟算式的负面对照先失败，再修复后通过。
- 真实 A6 旧 .so 无观测能力时仍输出 [20,-25]，trace 明确不完整。
- 独立审查复现删除全部 C 记录/篡改完成数与成功状态仍通过，以及提交缺关联；
  新增实际 C 回归先失败再修复，补跨阶段/节点/任务一致性与提交/关闭观测。
- 缺失 run.end 回归先复现校验器 AttributeError，再修复为返回失败报告。
- 补充真实 C 前输入失败、C 元数据失败、C 成功后主机复制失败和重试的准确记录测试。
- 独立只读复验确认原问题全部处理，无剩余 Critical/Important；未改代码、冻结样本或 Git。

## 最终验收证据

环境：WSL Ubuntu x86_64、Python 3.14.4、NumPy 2.3.5、GCC 15.2.0；
实际编译/加载 C，IR_REQUIRE_C=1 禁止缺编译器跳过。不是 Windows 原生 C 验收。

- 完整回归：105/105，无跳过，其中 A7 专项 15 项。
- verify-trace：54/54 包，追踪开启/关闭 54 次逐字节一致；stored/scalar/NumPy 共 162 比较通过。
- float32/int32 两条四节点链、A6 八项生命周期场景通过，包括数值失败重试、超时取消、
  丢失完成/取消确认、隔离恢复、FIFO、staging 上限及过期句柄。
- 主 trace：2978 事件，complete=true、dropped_events=0、recording_errors=0；
  导出 manifest 哈希、原始记录、摘要与时间线回读比对通过。
- 八种负面对照均被拒绝：缺节点、缺全部 C 记录、缺 run.end、伪造完成数、失败链改成功、
  不静止任务改成功、重复 C 链、节点乱序；均重排 seq/重算字节，不依赖简单长度差异。
- 观察溢出/观察异常两探针计算结果及释放均正确；对应 trace 不完整且不可验收通过。
- C 直接测试含 profile 容量/别名/输出保护；ASan/UBSan 通过，stderr 为空。
- 109 个冻结文件 SHA256 不变；报告 Python 源码、C 源码/测试、二进制哈希已核对。
- 54 样本设备退出前 live_tasks/live_sessions/staging 均为 0；场景路径各自清理。
- 审查独立探针确认重复模型/多会话正常，关闭和 GC 后不被 recorder 持有；
  ID/上下文/时钟观察失败不改变任务输出和资源归还，追踪标记不完整。

正式报告：build/a7_validation_final/report.json；全量日志：build/a7_unittest_final.log。
trace/ 下含 trace.json、timeline.json、summary.json、manifest.json；
observation_probes/ 保存预期不完整的观察故障证据，不与主 trace 混用。

复现命令（本目录 WSL/Linux，输出需改为不存在的新目录）：

    IR_REQUIRE_C=1 python3 -m unittest discover -s tests -v
    python3 -m inference_ref verify-trace --fixtures fixtures/synthetic-v1 --output build/a7_run_new

## 限制

只覆盖当前 PC 静态模型包、C 后端和逻辑设备路径，无真实模型/生成器/量化/硬件验收。
CPU clock 是进程 CPU 观测，host span 有嵌套及追踪开销；逻辑 tick 不是硬件周期。
内存统计非 RSS/全局峰值；没有第三方查看器 UI 验证。
原生 ASan/UBSan 检查 C 核心及观测接口，不是整个 Python 进程 sanitizer。
未提交、未推送，不修改冻结样本或其他项目。
