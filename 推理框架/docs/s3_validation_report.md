# S3 验证报告

2026-10-24；工具 0.3.0，平台 API 1，后端 API 1，C ABI/原有磁盘格式 1。
规格 platform.md，计划 s3_plan.md。

## 实现

PC 精确读取、受管对齐内存、主机单调时间源、host-coherent 同步接口与 uint64/32/64 位范围检查。
接入模型包读取、MemoryPlan、权重/会话生命周期、静态后端、模拟任务及追踪。
分配失败回滚，模型借用期间不能关闭；未知同步不返回输出或释放资源；确认后恢复。
不绑定具体模型、量化或 W4A8，不改冻结样本/C 数值核心。

## 测试过程

- 初始 8 项平台原语因缺接口 RED；读取/分配/范围通过后补齐可注入时钟。
- 6 项模型/会话/同步集成先复现无平台参数，再完成真实 C 集成。
- 部分释放失败允许重跑、缺少输出同步记录仍通过、读缓冲 MemoryError 未分类、
  直接时钟失败仍 complete=true、动态 size 重取可绕过限长均先复现，再做最小修复。
- Windows 平台原语 11/11 通过；第一次 WSL 完整回归 141/141 通过。
- 审查前新增至 22 项 S3 专项；最终完整计数、端到端与审查结果将在收口后记录。

## 独立审查与一次修复

只读独立审查给出 0 Critical、2 Important、1 Minor：
未知状态会话可随整个对象图被 GC 提前释放；binding.close 抛错后仍可能重跑；
同步 trace 未匹配所属 run 完整上下文。最后一项按对验收正确性的影响提升为 Important 同批处理。

三类均先由作者独立复现 RED，再修复：

- 新增可枚举 RetainedResource 强隔离登记，丢弃全部客户端句柄并 GC 后仍保留会话/模型/平台/块；
  无服务确认不能回收，确认与明确清理完成后撤销。
- 关闭开始即锁定，独立记录 binding 关闭成功；失败后不执行，重试确实再调用未确认的 binding.close。
- 同步证据匹配 run 的 model/session/task/device/platform/selected_backend；五类上下文错配均拒绝。

未追加第二轮独立复审；修复证明为上述 RED -> GREEN 回归与最终完整套件。
恶意插件隔离、RSS、真实 DMA/cache、RV32、S4 纯 C 不作为本轮证明；范围检查和普通时钟故障
未被审查发现需新增的问题。独立审查没有重跑全量/原生 C，以下均为作者实际运行证据。

## 最终验收

- 完整 **152/152**，无跳过，包含原 127 项与 **25 项 S3**。
- WSL Ubuntu x86_64 / Python 3.14.4 / NumPy 2.3.5 / GCC 15.2.0，IR_REQUIRE_C=1。
- 平台路径 **54/54** 样本、**162** 项参考比较通过；主追踪 **3458** 事件，完整且回读通过。
- 五探针通过：短读、uint64/目标32范围、部分分配失败、不可用时钟、输出同步/恢复。
- 缺少可见性同步、同步上下文篡改两种正式报告负面对照均被拒绝。
- 嵌套 S2 的 54 次显式回退/逐字节对照、两种身份负控，以及 A7 双链、八生命周期场景、
  观察故障与八语义负控、原生 C ASan/UBSan 全部通过。
- 主平台 live_allocations/backing_bytes/open_sources/retained_resources 全为 0，
  设备 live_tasks/live_sessions/staging 全为 0；故意拒绝恢复时则正确保留资源。
- 当前 Python 源码、C 源码/原生测试与库/测试二进制指纹核对一致；109 个冻结文件、
  全部 c/、S1/S2 封存清单与全部旧验收证据不变。
- 使用当前工具实际回读旧 S1/S2 trace，校验与派生文件比对通过。

正式证据：build/s3_unittest_final.log、build/s3_validation_final/report.json；
backends/report.json 和 backends/runtime_trace/report.json 为嵌套原路径证据。
build/s3_baseline.json / s3_baseline.sha256 固化版本、源码/文档/测试、冻结输入和验收指纹。
pre_review 与 first 日志保留为过程记录，不能替代最终源码指纹。

复现（本目录 WSL/Linux；输出必须使用不存在的新目录）：

    IR_REQUIRE_C=1 python3 -B -m unittest discover -s tests -v
    python3 -B -m inference_ref verify-platform --fixtures fixtures/synthetic-v1 --output build/s3_run_new

## 范围

32 位验证是地址/size_t 范围检查，不是 RV32 执行；高位 PC 指针不会截断为目标地址。
PC 同步不证明 DMA/cache/中断/硬件性能。arena/allocator 预算不是进程 RSS 或 S5 完整资源账本。
插件为受信进程内实现；读取不是并发编辑的事务快照；显式关闭与 GC 保证不同。
原有 S1/S2 清单和证据保留为历史，不作为本轮当前源码指纹；未提交、未推送。
