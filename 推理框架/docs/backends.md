# S2：可替换的静态整链后端

当前工具0.6.0，Python后端/平台API1。T3 CStaticRuntimeBackend要求native ABI2并按实际容量持有state/临时检查区，见t3_metadata.md。原磁盘包/样本/追踪version1、ir_core ABI1不变。ResourceGroup接入见resources.md。
本页描述 S2 整链边界；S3 当前平台入口见 platform.md；S1/S2 基线保留历史快照。
不绑定模型名称、量化、W4A8、分组或硬件路数。没有自动异构切图、实时设备驱动或执行失败重跑。

## 分层

- backend.py：不可变需求、能力报告、StaticBackend/BoundChain、注册表和策略。
- c_execution.py：CStaticBackend 包装旧 CBackend；CBoundChain 持有 ctypes 描述符/调用/profile。
- runtime.py：加载/计划/arena、输入准备、整链调用、输出与会话生命周期，不执行 C ABI 操作。
- sim_device.py：调度选定会话、私有输入快照和 lease；模拟器与实际数值后端分开。
- tracing.py：关联选择、实际执行和任务；generic 事件不伪造 C CPU 时间。

旧 create_session(model,CBackend) 与 SimDevice(CBackend) 自动包装为 ID=pc_c 的 CStaticBackend。
保留既有 C _calls 私有探针别名；运行时不靠该别名调度，非 C 后端不需要它。

## 接口

| 接口 | 行为 |
| --- | --- |
| requirements_for(package,plan) -> ChainRequirements | 复制每节点/绑定张量的 dtype、逻辑/存储形状、布局、角色、只读、memory_domain、attributes，以及整链 workspace/alignment/backing；无数值/指针 |
| StaticBackend.query(requirements) -> SupportReport | 纯能力查询，无分配/执行/所有权取得；每节点必须有 NodeSupport(index,node_id,supported,reason,workspace_bytes) |
| StaticBackend.prepare(package,plan,views,workspace,profile=False) -> BoundChain | 选择完成后绑定已分配 arena；不得修改只读权重/包/计划；失败须清理自身部分资源 |
| BoundChain.execute() -> ChainResult(status,completed_steps,quiescent=True) | 同步整链；正常错误也用结果返回，完成数表示已提交成功节点；OK 必须全链完成且确认静止 |
| BoundChain.observe_nodes() | 仅元数据观测；profiled 时返回全节点执行/失败/跳过；异常标追踪不完整，不改计算结果 |
| BoundChain.recover() -> bool | 异常后真实后端确认不再访问借用 arena 才能返回 True；默认 False |
| BoundChain.close() | 释放后端自己持有的描述符/资源，不能释放借用 arena；不得在未知执行中调用 |
| BackendRegistry(backends) | 1..32 个显式对象，唯一 ID/API 1；不从模型包动态加载代码，无隐藏全局注册表 |
| registry.query(requirements,id) | 验证报告类型、节点顺序/覆盖/理由、支持汇总与 scratch 容量；损坏报告报 INVALID_ARGUMENT |
| registry.select(requirements,policy) -> BackendSelection | 按显式策略查询；supported=False 时不产生绑定或会话 arena |

后端是进程内受信实现，不隔离任意 Python/本机指针写入，也不能以元数据证明插件计算正确。
首版绑定内存域为 host；其他域需要平台/驱动扩展，不把设备地址当主机指针。
C 适配器只支持原 float32/int32、row_major、linear/add/relu 和空属性集，检查形状、存储、
workspace、对齐和输出写权限；尚不识别的需求明确拒绝。当前模型包仍不接受量化/新算子。

## 显式策略与使用

    registry = BackendRegistry([preferred_backend, CStaticBackend(c_backend)])
    policy = BackendPolicy(preferred='preferred_id', allow_fallback=True, fallbacks=('pc_c',))
    session = create_session(model, registry=registry, policy=policy, trace=recorder)
    # 或 device = SimDevice(registry=registry, policy=policy, trace=recorder)

create_session(model,backend=None,*,registry=None,policy=None,memory_budget=...,trace=None)；
SimDevice(backend=None,*,registry=None,policy=None,config=None,trace=None)。
单 backend 与 registry 必须二选一；registry 必须带显式 policy。
BackendPolicy(preferred,allow_fallback=False,fallbacks=()) 是不可变配置；所有 ID 都必须注册且不重复。

| 情况 | 行为 |
| --- | --- |
| 首选全链支持 | 立即固定该后端，不查询后备 |
| 首选不支持、allow_fallback=False | 返回不支持；即使列出后备也不使用 |
| 首选不支持、显式允许且列出后备 | 严格按 fallbacks 顺序尝试，首个全链支持者被固定 |
| 全部允许候选不支持 | 返回逐节点原因；创建失败，不取得会话/任务 lease |
| ID 不存在、查询异常、损坏能力报告 | 配置/后端错误，传播并停止；不能当作“不支持”继续回退 |
| prepare/预算/数值/设备/输出复制失败 | 不重新选择、不重跑，保留实际完成计数和原错误语义 |
| execute 抛异常、伪 OK/非法完成数、未确认静止 | 状态未知；不返回有效输出，追踪标不完整；同步会话与模拟任务都隔离 |

session.selection 保存实际选择及尝试报告，to_dict() 返回纯元数据。
device.query_support(model) 返回相同支持/选择结果、operators 和逐节点原因，不创建会话。
创建后不会随策略自动切换后端，也不支持运行中替换注册表。
现有 MemoryPlan/arena 预算含义不变；后端额外资源需单独说明，本版不声称全局 RSS 上限。

## 异常与恢复

正常 NUMERIC_OVERFLOW 等结果已确认静止，但之前成功节点可能已提交；没有整图回滚。
generic DEVICE_ERROR 可以发生在节点之间或整链收尾：成功前缀后可全部跳过，
也可记录首个已进入的失败节点；全节点成功后设备仍可返回收尾错误，输出继续无效。
这不放宽原 C 数值错误必须匹配实际失败节点的规则。
execute 异常不被当作正常失败完成：Session.run 再次调用与 close 都报 BUSY，保护借用 arena。
直接会话用 session.recover() 请求 BoundChain.recover；非 True 或异常不解除隔离。
模拟设备仍经 recover -> RECOVERING；逻辑恢复结束时再取得会话后端确认。
拒绝/失败则回到 QUARANTINED，release/close 继续拒绝，staging 和 lease 保留。
C PC 同步实现没有后台执行，返回后可确认静止；这不是硬件 DMA/抢占/复位确认。

## 追踪

backend.select 主机阶段记录查询/选择异常；backend.selection 含 preferred_backend、
allow_fallback、fallbacks、完整 attempts、selected_backend、execution、used_fallback。
session.open、run 上下文、chain/node 和 task 状态都关联实际 selected_backend。
C 适配器仍发 c.chain/node；非 C 后端发 backend.chain/node，其时钟为 unavailable，
CPU ticks/duration 为 null。可测主机整链跨度，但不能把它当设备周期或逐算子 CPU 时间。
profile 缺失/观察失败仍执行选定后端，追踪明确不完整；不会换成另一个数值后端。
校验器读取旧日志，也检查新日志的候选顺序、支持理由、选择/会话/运行/任务及事件域一致性。
追踪 version=1 新增事件/可选元数据；旧工具不具备 S2 选择语义校验，应使用当前工具验收。

## 验收

WSL/Linux 项目目录，输出换成不存在的新名称：

    IR_REQUIRE_C=1 python3 -B -m unittest discover -s tests -v
    python3 -B -m inference_ref verify-backends --fixtures fixtures/synthetic-v1 --output build/s2_run_new

verify-backends 对 54 样本分别走直接 C 和“能力明确拒绝的测试候选 -> 显式回退 C”，
逐字节比较并对齐 stored/scalar/NumPy。test_denied 仅用于验证选择路径，不是硬件后端。
runtime_trace/ 另运行原 A7 的双链、8 场景、故障/负面对照、导出回读及原生 C sanitizer。
单元测试另覆盖非 C 测试实现、禁止回退、损坏报告/查询异常、prepare/后段数值失败、
未知执行与拒绝恢复、后端标识篡改和采集失败；这些测试实现不作为生产回退发布。
CLI 退出 0/1/2 分别为通过/验收失败/参数或工具或输出冲突。
S2 报告为 inference-backend-report / version=1；新增该验收报告不改变已有磁盘格式。
报告与实际 PC C 编译/源码/二进制指纹一起保存，不代表真实模型质量或板端性能。
最终 127/127 无跳过、54/54 与 162 比较通过；正式证据及独立审查限制见 s2_validation_report.md。
build/s2_baseline.json / s2_baseline.sha256 是 S2 当前内容快照，不能当作认证签名或 Git 发布。
