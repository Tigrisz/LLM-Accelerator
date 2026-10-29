# S2：可替换静态整链后端计划

依据：用户已确认 S2，原地实施；不提交/推送、不改冻结样本或 C ABI，不实施模型/量化/硬件配置。
沿用已批准的整链选择方案，无自动异构切图，无执行失败后的回退重跑。

## 规格与接口

- backend.py：不可变张量/节点/整链需求，逐节点能力报告；StaticBackend.query/prepare，
  BoundChain.execute/observe_nodes/close，ChainResult；BackendRegistry 与显式 BackendPolicy。
- c_execution.py：CStaticBackend、CBoundChain，独占 ctypes 描述符/调用/profile；旧 CBackend 自动适配。
- runtime.py：只管理模型、arena、输入/输出和生命周期；选择先于会话 arena/后端绑定。
  create_session(model, backend=None, registry=None, policy=None, ...)；旧调用保持兼容。
- sim_device.py：接受单后端或 registry/policy；能力查询返回完整尝试及选择结果。
  原队列、lease、等待/取消/隔离/恢复不变，实际执行固定为会话创建时选择的后端。
- tracing.py：backend.selection 记录首选/尝试/原因/实际执行；C 链仍用 c.*，
  非 C 后端使用 backend.chain/node，不能伪造 C CPU 时间；保持旧 version=1 兼容。
- backend_validation.py 与 verify-backends：54 样本直接/显式回退对照、参考比较、
  替换接口、拒绝/错误/资源/追踪验证与原 A7 全路径验收。

## 决策

- Ruling：默认禁止回退。仅首选静态 query 明确不支持且 allow_fallback=true 时按声明顺序尝试。
  未注册 ID、损坏报告、查询/prepare/execute 异常、预算/数值/设备失败不触发回退。
- Ruling：Python 后端 API 1，随工具 0.2.0 增加；磁盘/C ABI 仍为 1，S1 清单作为历史基线保留。
- Ruling：平台内存域仅 host；需求显式包含 dtype/layout/shape/storage_shape/角色/只读/属性及 workspace。
  不支持的域/属性不静默忽略；后端不得改模型包、计划或常量。
- Ruling：BoundChain 同步返回、正常结果必须确认静止。异常/损坏结果属于未知执行状态，
  模拟任务隔离，保留 lease；不凭异常猜测设备已停止。
- Ruling：保留原测试使用的 C 私有 _calls 别名，仅用于兼容既有探针；运行时执行不依赖该别名。

## 任务与验收

- [x] 1. 测试先 RED：能力原因/形状/dtype/layout/属性/内存、策略、未注册/损坏查询。
- [x] 2. 分离 C binding 和通用会话，真实 C/非 C 测试后端整链运行；原回归不倒退。
- [x] 3. 设备与追踪：选前拒绝无 lease、显式回退可追踪、数值失败不重跑、未知异常隔离。
- [x] 4. 54 样本/162 比较/双类型链和原生命周期追踪验收；完整测试、C sanitizer，输入/C 不变。
- [x] 5. 文档/版本/证据与一次独立只读审查完成；2 个 Important 已用 RED -> GREEN 修复并全量复验。

补充决策：generic DEVICE_ERROR 可发生在节点之间或整链收尾；保留真实成功前缀，
不要求伪造一个失败节点。原 C 错误的节点/完成数规则不变。
S2 selection 已存在时 session.open 必须保留身份字段，不因字段缺失降级为旧日志兼容。

Review focus：整链全支持才可绑定、假支持/假成功、选后异常触发隐藏重跑、未知异常提前释放、
generic 事件冒充 C 时间、观测异常改变执行、prepare/close 异常与资源归还。
进度 docs/progress.md；证据 build/s2_*。不改写 S1 指纹与历史报告。
