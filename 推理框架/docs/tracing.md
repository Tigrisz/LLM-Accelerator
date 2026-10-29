# A7：完整静态 PC 运行时追踪

当前工具0.6.0；trace/export/summary各自保持version1，ir_core ABI1。S5共享预算与缓存关闭见resources.md；S4独立C追踪另有格式，见static_runtime.md。
S3 可注入 host_monotonic/ns 时钟，并校验平台身份和输入发布/输出可见性同步；见 platform.md。
S2 增加 backend.selection 和 backend.chain/node，实际后端关联校验与边界见 backends.md。
Trace Event 时间线不另设本项目格式版本；S1 历史快照见 phase1a_baseline.md。

本轮覆盖 A1—A6 已实现路径：包加载和来源、MemoryPlan、会话、主机运行阶段、
实际 C 链和逐节点、模拟设备任务及释放。只观察元数据，不绑定模型、W4A8 或硬件参数。
不保存权重/输入/输出数值，也不把当前小型样本性能外推到实际模型或 FPGA。

## 开启方式

    trace = TraceRecorder()
    model = load_model(package_path, trace=trace)
    device = SimDevice(backend, trace=trace)
    session = device.create_session(model)
    handle = session.submit(feeds)
    waited = device.wait(handle, timeout_ticks=10)
    # 成功才 result；超时/取消/隔离仍按 A6 契约处理。
    outputs = device.result(handle)
    device.release(handle)
    device.close()
    trace.export(new_output_directory)

导入位置：inference_ref.tracing.TraceRecorder，runtime.load_model，sim_device.SimDevice。
同步 create_session(model, backend, trace=...) 也支持；省略 trace 时继承模型 recorder。
完整设备追踪需要把同一个 recorder 传给 load_model 和 SimDevice；
显式会话 recorder 不同时重新记录模型/计划，避免把另一个日志的模型 ID 当作本日志对象。
未开启追踪时沿用普通 C 链；没有全局开启状态或隐藏回退。
inspect_model、独立参考运算、直接任意 C API 调用不自动插桩。

## 关联和事件

模型加载实例 model_ref、会话 session_ref、执行 run_ref、设备 device_ref 为追踪内唯一标识，
不拿包 model_id 作为实例标识。task_ref 使用 A6 设备命名空间 UUID + task_id。
run_ref 关联会话和本次 execution_id；重试和重复运行不会混用前次 C 节点记录。

| 事件 | 内容 |
| --- | --- |
| model.load.begin/end、model.loaded | 加载尝试/状态、包名、清单和权重 SHA256、输入输出 ID |
| model.tensor/node | dtype、逻辑/存储形状、角色、大小、算子及绑定关系 |
| memory.plan/placement | 三类 arena/对齐额外空间/总 backing、偏移/容量/闭区间/复用资格 |
| session.open/close | 会话关联、实际 arena backing、profile 缓冲大小、关闭状态 |
| run.begin/end | execution_id、状态、实际完成节点数；异常路径也记录 |
| run.validate/prepare/outputs | 主机阶段及错误状态 |
| c.chain | 实际 C 链返回状态、完成计数、节点数、是否有逐节点观测 |
| c.node | 节点索引/ID/op/dtype、执行/失败/跳过、CPU 时钟有效性和时间 |
| device.* | 查询、创建、提交、轮询、等待、推进、取消、恢复、读取、释放、drain/quiesce/关闭的结果；device.session.close 包括 BUSY 拒绝 |
| task.accept/state/release | 模型/会话/任务关联、状态、静止/可见性、故障标签、staging 预留 |

A6 原 TaskEvent 和协议保持；追踪不会在 TIMEOUT、CANCEL_REQUESTED 或 QUARANTINED 时释放 lease。
提交尝试关联会话/模型，成功返回后补 task_ref；拒绝提交不会伪造已接受任务。
device.wait 的 API status=OK 表示调用正常返回；wait_status 区分 COMPLETED/TIMEOUT/DEVICE_ERROR，
计算是否成功仍看 task.state/status，不能混淆。

## 三种时间域

1. 主机：perf_counter_ns，相对 recorder 创建点，记录事件 t_ns 及阶段 start_ns/duration_ns。
   它包含 Python/ctypes/校验等主机开销；嵌套跨度会重叠，不能直接全部相加。
2. C 节点：ISO C clock() process CPU ticks，以 ir_clock_ticks_per_second 转换为 ns。
   这是进程 CPU 观测，可能包含进程其他活动和 clock 调用开销，分辨率不等于 1ns。
   小算子可能测得 0；不可用/回绕时 timing_valid=false，时间和 ticks 为 null。
3. 模拟器：logical_tick 和各阶段 tick 差，只有协议顺序/延迟意义，不是毫秒或硬件周期。

三个域分开保存与统计；不把 CPU ticks 或逻辑 tick 放进主机时间线坐标。
timeline.json 采用 Trace Event 格式，主机跨度 ph=X、主机时间转换为微秒 ts/dur；
C 节点是瞬时事件，CPU 时长只在 args 中，displayTimeUnit=ns 不改变 ts/dur 的微秒约定。
可以交给支持 Chrome Trace Event JSON 的时间线查看器；本轮验证文件结构与回读一致性，
未做第三方查看器 UI 的兼容性测试。

## C 观测 ABI

原 ir_abi_version=1、ir_tensor、ir_call 和 ir_execute_chain 保持兼容。
新增 ir_node_profile（32 字节）、ir_profile_struct_size、ir_clock_ticks_per_second、
ir_execute_chain_profiled(calls,count,completed,profiles,capacity)。
普通/观测路径共享链元数据校验与执行，C 不接收 expected 或 Python 计算结果。
profiled 路径为每个实际 ir_execute 前后采样；失败节点 executed=1 并保存真实状态，
之后节点 executed=0。元数据失败不写 profiles；Python 每次调用前清空，以免复用旧记录。
profile 存储区必须独立于计数器、调用数组、描述符、全部声明张量容量及工作区。
容量不足/非法区间/别名在任何写入之前拒绝；实际内存和指针真实性仍由调用方保证。

CBackend 动态探测可选观测能力。旧库缺少扩展时仍可普通 C 执行，
但追踪 complete=false，不能冒报获得逐节点数据。已用实际 A6 旧 .so 验证此路径。
profile 数组每会话最多 1024*32 字节，独立于 A5 arena 预算；关闭会话时释放。

## 有界采集与非干扰

TraceRecorder(max_events=16384,max_bytes=16MiB)；可配置事件数 0..1000000、JSON 事件字节 0..64MiB。
预算覆盖保留的紧凑 JSON 事件，不是整个 Python 对象堆、导出副本或进程 RSS 上限。
记录时复制为 JSON 元数据，不保留模型、张量或任务对象；snapshot 返回独立副本。
收集器用锁与 ContextVar 隔离调用上下文；A6 仍仅允许设备所有者线程使用，未变成并发设备。

缓冲区满时拒绝继续保存并增加 dropped_events；常规观察错误增加 recording_errors。
complete 仅在二者均为 0 时为 true，表示已启用采集范围没有已知缺失，不保证外部未插桩代码覆盖。
安全记录函数不传播常规追踪异常到数值/任务执行；不吞掉应用的 KeyboardInterrupt/SystemExit。
CPU profile 缓冲申请失败或旧库能力缺失时执行普通 C，并标记观察不完整。
追踪本身有耗时和额外内存；本轮只验证开关结果与状态一致，不承诺零开销。

## 格式、导出与校验

trace.json：format=inference-runtime-trace/version=1、trace_id、时钟、预算/丢失/错误/complete 及 events。
每个事件含连续 seq、相对 t_ns、kind、context、data；主机跨度另含 start_ns/duration_ns/duration_clock。
CPU/逻辑时钟只出现在显式字段，节点实际跳过时不会伪造执行时间。

export(new_directory) 只写不存在的新目录，输出 trace.json、timeline.json、summary.json 和 manifest.json。
manifest 记录三文件长度与 SHA256。read_export 校验文件/哈希并重建摘要/时间线比对，
validate_trace 校验顺序、时钟算式、模型/会话/run/任务关联、逐节点元数据及完成计数。
成功 run 必须有唯一 C 链、正确的节点执行顺序和输出阶段；失败节点后只能跳过。
区分 C 前主机失败、C 元数据/数值失败与 C 成功后主机输出复制失败。
任务检查合法转换、lease、进度、静止与结果可见性；成功任务必须关联成功 run。
丢失 C/结束记录、伪造完成数/成功状态、重复链、会话关联和 CPU 算式不一致，
即使重排 seq 并重算字节长度也会失败；畸形记录返回失败报告。
哈希是内容一致性，不是认证签名；导出中断可能留下不完整目录，不承诺目录级原子发布。

validate_trace 默认 require_complete=True；不完整采集不可验收通过。
调试可用 require_complete=False 查看前缀记录，complete 标记仍保留，不把未知算作成功。
summary 包含算子执行/失败/跳过、有效 CPU 样本及总/最小/最大时长、主机跨度、等待结果、
逻辑阶段 tick、已释放任务状态、计划和最大观察会话 backing/staging。
最大会话 backing 是“模型+一个会话”的观察最大值，不是全局存活峰值/RSS；模型权重 GC 未追踪。

## 验收命令

WSL/Linux 本目录：

    IR_REQUIRE_C=1 python3 -m unittest discover -s tests -v
    python3 -m inference_ref verify-trace --fixtures fixtures/synthetic-v1 --output build/a7_run_new

Windows PowerShell：

    wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec env IR_REQUIRE_C=1 python3 -m unittest discover -s tests -v
    wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec python3 -m inference_ref verify-trace --fixtures fixtures/synthetic-v1 --output build/a7_run_new

报告 source=pc_runtime_trace、execution=simulated_device_c。54 个样本逐字节比较追踪开关，
并对齐 stored/scalar/NumPy；双类型四节点包、A6 八场景、溢出/观察失败探针及八种语义负面对照。
主 trace/、不完整 observation_probes/ 均可回查；最终报告和 C 构建/sanitizer 证据在同目录。
退出码 0 全部验收通过，1 数值/追踪验收失败，2 参数/工具/输出冲突。
这完成当前阶段 1A 支持集的 A7，不代表真实模型生成、RV32/FPGA 或硬件性能验收。
