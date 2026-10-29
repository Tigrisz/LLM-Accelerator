# S5 运行时资源账本

工具0.6.0，ResourceLedger API1。T3纯C native ABI2，按T提供状态/检查区并计c_metadata，检查区借用至bind返回；见[t3_metadata.md](t3_metadata.md)。模型包/执行描述、ir_core ABI和平台/后端回调仍为1。
**C PC服务结构 irs_pc/irs_block 扩展为 IRS_PC_SERVICES_ABI=2，使用ir_pc.h的原生调用方必须重编译**；
不宣称这些具体PC结构与S4二进制布局兼容。原ir_core三份头/源码/测试不修改。

## 计量口径

ResourceLedger记录**受管有效载荷与记录数**，不是进程RSS，也不估算所有Python对象/分配器内部开销。
`live_bytes`是当前预算预留；`resident_bytes`是已存在、在本类别口径下可计量的载荷；
`peak_bytes/peak_resident_bytes/peak_count`是对应账本生命周期峰值，不在释放后清零。

| 分类 | 字节/数量口径 | 释放时机 |
|---|---|---|
| arena | 实际NumPy backing字节，包含alignment-1预留；weight/activation/workspace共享同一分类 | block确认释放；共享权重只计一次 |
| c_metadata | ctypes原生tensor/call/completed、context/执行描述和T字节状态；T3绑定时另分配4T字节检查区 | prepare失败回滚或binding确认关闭；检查区在bind返回释放 |
| c_profiles | 原生profile表的sizeof容量 | binding关闭；预算不足禁用profile并标记追踪不完整 |
| trace | 内部已缓存事件的规范JSON编码字节与事件数；不是Python字典的堆大小 | recorder.close；不会随Session关闭虚假归零 |
| task_staging | 提交时预留输入快照+最大逻辑输出字节；resident随实际输入/输出持有变化 | task确认静止并release |
| task_records/session_records | 活跃记录数量，字节字段0表示未估算Python对象大小 | 相应记录释放/关闭 |
| task_events | 当前保留历史事件数量 | task release；溢出只累计dropped，不无限扩展 |

PC模型包解析/导出工作区、原始Python ModelPackage及其weights bytes、Python容器/ctypes包装器、
共享库/栈帧/allocator开销、用户feed/result/snapshot/export副本不纳入上述有效载荷预算。
这些在PC端确实占内存；本账本的0不等于RSS归零。纯C host对自己的文件/输入缓冲也做分类计账。
T3检查区是明确的caller-owned载荷；编译器frame、调用链及整个线程栈峰值另测，不能拿检查区大小代替。

## 接口

```python
ledger = ResourceLedger(budget_bytes=64*1024*1024,
                        byte_limits={'c_metadata': 1024*1024},
                        count_limits={'task_records': 16})
platform = PCPlatform(ledger=ledger)
trace = TraceRecorder(ledger=ledger, clock=platform.clock)
model = load_model(path, platform=platform, trace=trace)
```

显式共享ledger才能统一预算：TraceRecorder不传ledger时使用独立的trace账本；
SimDevice任务采用其Session平台的账本，没有显式platform时取model.platform。
可通过`platform.resource_info()`、`session.resource_info()`、`device.resource_info()`和`trace.resource_info()`查看。
原memory_info/设备stats字段及原arena budget含义保留；新的全局预算使用ResourceLedger。

`reserve(category,bytes,resident_bytes=0,count=1,label='')`返回唯一持有的Reservation。
`resize`原子检查增长；拒绝不改变既有账目，`close`幂等；普通GC可释放失去持有者的reservation。
`byte_limits/count_limits`是分类上限，`budget_bytes`是各分类预留字节总上限；数量不换算为虚构字节。
支持uint64检查和max_entries上限，labels最多128字符。`fail_after=N`在N次新建/增长后注入RESOURCE_LIMIT，
缩小与释放不受故障注入影响；用于PC验证，默认关闭。

平台arena先预留后分配，失败撤销。C后端通过prepare_resources上下文和ResourceGroup接入，
不改既有prepare签名；每个native缓冲先预留再创建，已完成的部分在失败时清理。
第三方后端须接入ResourceGroup或自行实现相同生命周期；不能据此推断任意后端内部均已计量。

## 生命周期与观察失败

未知backend/sync状态保留Session及C元数据；未知模拟任务额外保留整个Device对象图，
防止GC释放task快照/记录/lease。`retained_resources(platform_id)`可找回资源所有者，
所有相关服务确认恢复后才允许继续释放。close失败会阻止重跑并保留尚未释放的账目，重试完成后扣除。

终态任务在release前仍持有staging预算，取消/失败不提前释放。结果副本交给调用方后不归task账本持有。
SimConfig.max_task_events默认128、范围1..4096；达到本地或账本历史上限后状态机继续，
`device.resource_info().dropped_task_events`明确报告当前任务历史截断，原TraceRecorder仍独立观察状态。

trace/profile预算拒绝不更改算术状态：丢事件/禁用profile并标记不完整。
TraceRecorder.close必须在snapshot/export之后调用；释放缓存后不能继续record/snapshot/export，close可重试且幂等。
取得的snapshot/export文件属于调用方，关闭内部缓存不会销毁它们。

## 纯C计账

irs_pc_alloc_kind按arena/metadata/profile/trace/task/source分类，irs_pc_reclassify转移分类时不重分配；
包含对齐开销，记录当前/峰值/分类预算/拒绝计数，irs_pc_free只允许owner释放。
irs_pc_check_transient在同步调用前检查已知栈工作集并记录预留峰值；不分配堆，也不改变当前堆余额。
T3 host按实际T分配检查区并在bind后释放，trace JSON包含context/state/检查区和分类统计；标准库FILE缓冲不在显式账本中。irs_pc_check_transient仍可用于其他已知临时预算，不再用于固定inspect数组。
纯C执行过程仍不依赖Python，编译和离线验收需要PC工具。

## 验收

```text
python3 -B -m inference_ref verify-resources --fixtures fixtures/synthetic-v1 --output build/s5_new --iterations 200
IR_REQUIRE_C=1 python3 -B -m unittest discover -s tests -v
```

verify-resources嵌套S4的54样本、双类型四节点链、独立C与适配对照和普通/ASan/UBSan。
额外覆盖两后端×两类型×三会话重复任务、8分类预算、20点/后端故障扫描、
拒绝恢复50次后的事件上限/GC保留/确认释放、close重试。原生C各跑1000次并覆盖6个分配失败点。
PC验证不等于硬件、RV32、DMA/cache/FENCE或具体模型/量化配置验收。
