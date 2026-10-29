# A6：模拟设备后端与任务生命周期

当前工具0.6.0；平台/后端API1，没有独立设备线协议版本。S5记录/staging预算与history上限见resources.md，S3见platform.md，S4见static_runtime.md。
继承的模型包 version=1、C ABI=1；S2 整链选择/恢复确认见 backends.md。

实现 inference_ref/sim_device.py；延续 model-package-v1、MemoryPlan 和 A4 C ABI。
显式使用 SimDevice 才进入模拟器，无模型名称分支、W4A8 配置或隐藏 Python 数值回退。
默认设备任务执行 A5 Session.run -> A4 C 链；S2 也接受显式 registry/policy 或 StaticBackend。
能力与实际执行后端以 query_support 和会话 selection 为准；现有包仍只支持 FP32/INT32 三种算子。

## 执行方式

这是单所有者线程、显式逻辑时钟的协作式模拟器，没有后台线程或真实设备。
submit 只校验/快照和排队；poll 只观察；advance / wait / drain / quiesce 才推进模拟事件。
设备只有一个执行槽，有界 FIFO；各会话拥有独立的 A5 激活/scratch，共享只读模型权重。
同步 C 调用整体不可抢占，取消只能在模拟事件边界受理，不能声称已验证真实计算中途抢占。

SimConfig 的 transfer_ticks、compute_ticks、sync_ticks、cancel_ticks、recovery_ticks
均为 1..100000 的整数，默认 1。一个正常任务默认经历：

    tick 0: submit -> QUEUED
    tick 1: 调度 -> TRANSFERRING
    tick 2: 传输阶段结束 -> RUNNING
    tick 3: 执行完整 C 调用链 -> SYNCING
    tick 4: 可见性/完成确认 -> SUCCEEDED

传输和可见性阶段是协议模拟。submit 时已复制输入，实际复制到执行 arena 由 A5 run 完成；
并没有 DMA、cache clean/invalidate、MMIO、UART 或硬件完成中断。
逻辑 tick 不是毫秒、周期、C 计算超时或性能测量。wait 无法在同步 C 调用内部抢占。

## 状态与确认

| 状态 | 含义 | 可读输出 / 可 release |
| --- | --- | --- |
| QUEUED | 已接受、私有快照已持有 | 否 / 否 |
| TRANSFERRING | 模拟输入传输 | 否 / 否 |
| RUNNING | 等待并执行真实 C 链 | 否 / 否 |
| SYNCING | C 已返回，尚未发布完成/可见性 | 否 / 否 |
| CANCEL_REQUESTED | 已请求取消，等待停止确认 | 否 / 否 |
| QUARANTINED | 未确认静止，隔离且阻塞设备执行槽 | 否 / 否 |
| RECOVERING | 恢复已发起，等待模拟器确认静止 | 否 / 否 |
| SUCCEEDED | 成功、输出可见、确认静止 | 是 / 是 |
| FAILED | 错误且已确认静止 | 否 / 是 |
| CANCELLED | 取消已确认静止 | 否 / 是 |

终态仅 SUCCEEDED / FAILED / CANCELLED，均 quiescent=true。
QUARANTINED 不是终态。quiescent 表示模拟协议已确认，而不是推测没有主机线程在运行。
同一所有者线程串行决定取消/完成竞争：先成功完成则 cancel 保持成功及有效输出；
先接受取消则不再公布成功。重复 cancel 不重置确认延迟。
即便在 SYNCING 取消，也丢弃已算出的结果；completed_steps 仍记录实际 C 完成节点数。

TIMEOUT 属于 wait/drain 的 wait_status，不写成任务失败，不隐式取消，不释放 lease。
等待结果为 COMPLETED（查看 task.status 判断成功/失败/取消）、TIMEOUT 或 DEVICE_ERROR
（任务隔离，需要显式恢复）。poll 和 timeout_ticks=0 不推进时钟。

## 所有权、内存和限制

提交被拒绝不会修改会话、取得 lease、占用任务额度或 staging 预算。
接受后私有复制全部输入；调用方可在 submit 返回后修改自己的原数组。
调用期间仍须保持 feeds 不变，不把可变内部对象作为安全隔离边界。
每个接受的任务持有整个 A5 会话 arena lease，直到终态静止并 release。
任务未 release 时，同会话再次提交、关闭会话和关闭设备均 BUSY，成功任务也一样。
result 返回独立副本；用户修改该副本不会影响任务保存的结果。

默认 max_tasks=16、max_sessions=16，均可设为 1..1024；任务上限含未释放终态记录。
staging_budget 默认 64MiB，预留输入快照总 nbytes + 最终输出逻辑 nbytes，
任务释放时归还，排队/等待/取消/隔离期间都不能提前归还。
这与 A5 模型+单会话 arena backing 预算分开；不含 Python 对象、C 描述符、
返回给调用方的 result 副本，也不是进程 RSS 或全局会话 arena 总上限。
所有者线程检查阻止其他线程访问设备 API；这里不提供线程安全任务队列。

## 接口

TaskHandle(device_id, task_id) 为 frozen 值，设备命名空间 UUID + 单调 uint64 ID，不复用。
过期、跨设备、错误类型句柄均 INVALID_ARGUMENT；不是跨进程鉴权令牌。
TaskSnapshot / TaskEvent / WaitResult / DrainResult 也为 frozen 观察结果。

| API | 行为 |
| --- | --- |
| SimDevice(CBackend, config=SimConfig(...)) | 显式模拟设备；必须有真实 C 后端 |
| query_support(model) | 返回静态支持集及实际执行后端 pc_c_backend；创建会话还执行 C 元数据查询 |
| create_session(model, memory_budget=...) | 复用 A5 规划及预分配，返回设备注册的 SimSession |
| session.submit(feeds, fault=None) / device.submit(session, feeds, fault=None) | 精确校验后快照并返回唯一句柄 |
| poll(handle) | 不推进时钟，返回不可变状态快照 |
| events(handle) | 返回最小生命周期事件元组，记录逻辑 tick/状态/计数 |
| advance(ticks=1) | 推进 0..100000 个模拟 tick |
| wait(handle, timeout_ticks=0) | 最多推进预算 tick；完成不等于成功，需看 task.status |
| cancel(handle) | 先 CANCEL_REQUESTED，等待确认；已完成任务保持原终态 |
| result(handle) | 仅成功、可见且静止后复制输出 |
| release(handle) | 仅终态静止后释放私有快照/结果和 lease，句柄立即过期 |
| recover(handle) | 仅 QUARANTINED；进入 RECOVERING，之后由 advance 确认静止 |
| drain(timeout_ticks=0) | 等待全部任务静止；不自动 release；有隔离任务返回 DEVICE_ERROR |
| quiesce(timeout_ticks=0) | 请求取消全部未完成任务，再 drain；不会假装取消隔离状态 |
| stats() | 当前逻辑时钟、执行槽、记录数和 staging 预留量 |
| session.memory_info() | 只读观察 A5 arena 地址/backing 大小，不暴露可写数组 |
| session.close() | 必须无任务 lease；幂等 |
| device.close() / with device | 必须无任务记录；关闭剩余空闲会话；幂等 |

设备和会话上下文退出不会通过超时、自动遗忘任务来规避 BUSY。
应先 wait/result 或 quiesce，确认终态后 release，再关闭。
未注册的 SimSession 包装不能提交、读取 arena 信息或关闭底层会话，防止绕过 lease。

## 故障与恢复

只允许固定 fault 标签，不从包加载代码或任意故障回调：

- device_error：C 实际返回后注入已确认的设备错误；FAILED/DEVICE_ERROR，不发布结果。
- lost_completion：C 实际返回后模拟完成/静止确认丢失；QUARANTINED，保留全部 lease/预算。
- stuck_cancel：收到取消请求后模拟停止确认丢失；QUARANTINED。

真实 C 数值错误保留原状态码及 completed_steps，已确认调用返回所以 FAILED/quiescent。
意外执行异常进入 QUARANTINED，禁止按普通失败释放；KeyboardInterrupt/SystemExit 也先隔离再传播。
通过 A5 execution_id 区分本次 run 和历史记录；异常时保留本次已经确认的 C 完成计数，
若尚未进入本次 run 则保持 0/未知，不借用前一次成功进度。
在进入 run 前发生的拒绝也保守隔离，不用 BUSY 等异常推断底层已经静止。
recover 不接受“调用方确认静止”的布尔参数。模拟器在恢复延迟结束时确认停止，
转为 FAILED/DEVICE_ERROR 后才能 release。恢复不会把旧结果变成成功或自动重跑任务。
确认静止后 release，再用纠正的输入新建任务，复用同一 A5 arena。

这是设备协议的模拟验证；真实驱动必须用硬件停止/复位/隔离协议替换恢复确认。

## 使用与验收

应用先使用 A4 build_backend / CBackend 和 A5 load_model，然后：

    device = SimDevice(backend)
    session = device.create_session(model)
    handle = session.submit({输入ID: ndarray})
    waited = device.wait(handle, timeout_ticks=10)
    # 只有 waited.task.state == "SUCCEEDED" 才 result；TIMEOUT 继续等或显式 cancel。
    outputs = device.result(handle)
    device.release(handle)
    session.close()
    device.close()

WSL/Linux 本目录运行：

    IR_REQUIRE_C=1 python3 -m unittest discover -s tests -v
    python3 -m inference_ref verify-device --fixtures fixtures/synthetic-v1 --output build/a6_run_new

Windows PowerShell：

    wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec env IR_REQUIRE_C=1 python3 -m unittest discover -s tests -v
    wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec python3 -m inference_ref verify-device --fixtures fixtures/synthetic-v1 --output build/a6_run_new

输出目录必须不存在且在 frozen fixtures 之外；退出码 0 通过，1 验收失败，2 参数/工具/输出冲突。
报告 source=simulated_device_c，记录 54 样本/162 比较、两条四节点包、8 项生命周期场景、
输入不变、逻辑事件、内存计划和实际 C 编译/源码/二进制/ASan/UBSan 证据。
source 不标为实板，逻辑 tick 不推导真实设备性能。A7 追踪现已接入，开启方式见 tracing.md。
