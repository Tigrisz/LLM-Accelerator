# S5 验证报告

2026-10-25；工具0.5.0，资源账本API1。规格resources.md，实施记录s5_plan.md。
原模型包/执行描述、ir_core ABI和平台/后端回调仍为1；C PC服务具体结构ABI2，原生调用方须重编译。

## 完成内容

ResourceLedger统一全局/分类字节预算、分类记录上限、当前/驻留载荷/峰值与故障注入；
arena含对齐backing，C元数据含原生描述符/call/context/执行描述及绑定inspect固定工作集，
profile、trace缓存、task staging/record/event、Session记录分别计账。
共享权重只记一次；先预留再分配，失败回滚；未知状态或关闭未完成不提前扣账。

TraceRecorder支持共享账本与显式close；可选观察预算不足标记不完整，计算仍可成功。
任务历史max_task_events默认128，反复恢复不无限增长；未知Device整个对象图可通过
retained_resources找回，避免仅保留Session arena却丢掉任务快照/lease。

纯C PC allocator新增分类/峰值/拒绝统计、分类预算、无重分配转移分类及固定栈工作集预检。
独立host追踪附资源摘要，运行仍不依赖Python。未修改ir_core.h/ir_core.c/test_core.c或109个冻结输入。

## 最终端到端与压力验证

WSL Ubuntu x86_64 / GCC15.2.0 / Python3.14.4 / NumPy2.3.5。

- `verify-resources --iterations 200`：**24/24压力探针通过**；嵌套S4 **54/54样本、162参考比较**，
  独立C与适配输出逐字节相同，INT32/FP32两条四节点链正常/零输入及sanitizer运行通过。
- 两种C后端×两种dtype×三会话×200轮：**2400个成功任务**，输出均为手算[20,-25]，
  arena地址稳定，释放任务后的账本基线不增长；另覆盖lost_completion/stuck_cancel/device_error。
- 四个压力账本峰值分别为37656、37693、115813、115825字节；每个最终live_bytes/resident_bytes/live_entries均0。
  峰值是该受管口径的实测值，追踪事件的时间戳编码长度会造成少数字节差异，不是性能指标或RSS。
- 两后端各20个fail_after位置：**40个故障扫描位置**跨越拒绝/成功边界，所有已持有资源最终归零。
- 两后端各8分类预算探针：arena/c_metadata/task_staging与record预算拒绝正确回滚；
  c_profiles/trace/task_events预算不足不改变数值，观察或历史截断明确报告。
- 两后端各**50次拒绝恢复**，事件历史限8、丢弃96条，整图GC后仍保留staging与记录；
  确认恢复后释放；每个另注入一次close失败，第二次关闭成功，资源归零。
- 原生C资源压力程序在普通与**ASan/UBSan**下各跑**1000次小型add链**，运行期间无新增受管分配；
  6个分配失败点、分类/总预算、未知同步拒绝关闭、确认恢复均通过，stderr为空。
  最终live_bytes=0，包含inspect预留工作集的峰值54450字节。
- 读取**62份**成功独立C追踪，检查分类余额全部0、ABI2、固定工作集32768字节及峰值一致性。
- 嵌套适配追踪3786事件完整、导出回读通过；原S4的5个追踪负控仍拒绝。
- Windows Python3.12.14/NumPy2.3.5：账本与PC平台基础测试**5/5**通过。

完整回归**174/174、无跳过**，89.775秒，日志build/s5_unittest_final.log；
S5专项13项，独立审查回归包含在全量测试中。

## 独立审查及一次修复

一次只读独立审查：0 Critical、2 Important、0 Minor。

1. 原C绑定先创建临时CCall列表/shape数组，再创建最终表，漏计瞬时原生载荷。
   回归分别捕获CCall/CTensor带临时结构初始化路径；修复为直接分配已预留的零初始化表并逐字段填充。
2. S4绑定先分配可选profile再预留必需inspect栈，观察开关可使同预算会话准入失败。
   回归以无profile必需峰值作为精确全局预算，开观察原先失败；修复后先持有必需栈预算，
   无余量时禁用profile、标记不完整，数值仍成功。

两项均先RED再GREEN，修复后专项13/13通过。未进行第二轮独立审查；由作者回归和最终验收验证修复。
审查未穷尽第三方分配器/后端行为，未验证真实硬件、DMA/cache或RV32。

## 证据与口径限制

- build/s5_validation_final/report.json：24探针的分类账本、峰值、故障位置和恢复结果。
- build/s5_validation_final/static_runtime/report.json：54样本、双链、三种原生测试普通/sanitizer及构建指纹。
- build/s5_unittest_final.log：全量回归；build/s5_baseline.json及.sha256：最终内容指纹。

账本覆盖明确受管载荷/记录数，不是RSS；Python容器与包装器、原ModelPackage/weights bytes、
加载/导出的临时工作区、调用方feed/result/snapshot副本、libc/共享库和未知线程栈开销不计。
固定C inspect工作集是可查询的预留，不是整个栈的测量。未接入ResourceGroup的自定义后端不能推断已完整覆盖。
TraceRecorder默认有独立账本；需要显式传同一ledger才共享预算；关闭前缓存仍占账，关闭后禁止继续录制/导出。
保留PC验证边界，不绑定具体模型或W4A8；未提交/推送，未实施S6或板端服务。
