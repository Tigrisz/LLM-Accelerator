# 阶段 1A 接口契约 v0.5.0

状态：A1—A7 与 S1—S5 当前 PC 静态支持集已实现；资源预算见resources.md，纯 C 见 static_runtime.md。
文档修订 v0.5.0、工具0.5.0，资源/静态C运行时/平台/后端 API1、磁盘格式1、ir_core ABI1分开编号。
C PC服务irs_pc/irs_block具体结构为ABI2，原生调用方须重编译，不混同于不变的服务函数表API1。
静态包/会话和模拟设备已有实现；完整生成会话、板端平台和真实设备仍为设计。
A4 另已实现 PC C 同步算子/顺序调用链，接口细节见 c_backend.md 和 c/include/ir_core.h。
A5 已实现 PC 静态包加载/内存规划/同步算子图会话，见 model_package.md；
下文 token 生成会话接口、板端平台和设备服务仍为设计。
A6 已实现 PC 协作式模拟设备和任务生命周期，见 sim_device.md；不代表实际设备驱动。
A7 已接入当前静态运行时追踪，见 tracing.md；host/CPU/逻辑时钟分离，观察不完整明确标识。
S2 已提炼整链 StaticBackend/BoundChain 与显式策略，不再要求通用会话绑定 CBackend 类型。
S3 已实现 PC 平台读取/对齐内存/主机时间/同步；板端平台服务仍未实现。
S4 已实现 PC 离线导出与纯 C 静态执行；模型包JSON解析/规划仍在离线端，不要求目标机运行Python。
S5 已实现分类资源账本/共享预算/峰值与压力测试；计量口径为受管载荷和记录数，不是RSS。
S6接入准备资料/模板v1见model_intake.md；当前能力与差距见capability_matrix.md、model_gap_analysis.md。
S6不改变本契约或运行时0.5.0的实际执行支持，未填写需求不得判为模型可接入。

## 模块与依赖

离线准备工具 -> 样本/模型包 -> 模型适配器 -> 会话执行 -> 算子调度 -> 后端。
张量/内存服务贯穿执行链；平台提供读取、计时和设备同步；追踪工具只观测结果。
静态执行核心使用 C，离线检查/规划和参考工具使用 Python/NumPy，不引入具体模型依赖。
模型结构由适配器实现；硬件后端实现算子，不解释模型名称。

## 通用状态与错误

接口必须返回成功或明确错误，不以空输出冒充成功。
错误至少包括 INVALID_ARGUMENT、INVALID_SHAPE、UNSUPPORTED、RESOURCE_LIMIT、
INVALID_FIXTURE、CHECKSUM_MISMATCH、NONFINITE、NUMERIC_OVERFLOW、IO_ERROR、
ALREADY_EXISTS；设备阶段另有 BUSY、DEVICE_ERROR、TIMEOUT、CANCEL_REQUESTED。
Python 子集通过 ContractError.code 表达；未来 C 状态码映射保持含义而非 Python ABI。
不支持的算子、格式或布局在执行前拒绝，禁止静默改变精度或后端。

## 张量与缓冲区

逻辑形状表示有效元素；存储形状表示含 padding 的物理布局。
每个维度是正整数（bool 不算整数），逻辑/存储 rank 相同且逻辑维度不大于存储维度。
完整契约还包含 dtype、layout、量化格式版本、buffer handle、offset、length、
alignment、读写权限、所在内存域。运行时 buffer handle 不写入磁盘包。
文件偏移/容量运算采用至少 64 位无符号语义并检查乘加溢出；
映射到 RV32 地址时检查地址空间和 size_t 范围，禁止截断。

缓冲区分为：模型只读权重、会话持久状态、算子临时工作区、设备共享区。
所有者负责释放；引用者只能在声明的生命周期内借用。
会话执行前预留预算，工作区按生命周期复用；不依赖每 token 无界动态分配。
设备任务持有的输入/输出在确认设备静止前不得修改、释放或复用。
CPU 地址、文件偏移、设备地址属于不同命名空间。

量化描述必须包括：编码版本、位宽/符号、packing、分组轴/大小、scale 布局、
zero point、舍入、饱和、累加及输出转换规则。“INT4”单个标签不表示兼容。
padding 编码为对应格式的数值零，非对称量化不保证是二进制零。
本轮不实现量化执行；未声明的格式返回 UNSUPPORTED。

## 完整模型与生成会话接口（设计，未实现）

| 操作 | 输入 -> 输出 | 约定 |
| --- | --- | --- |
| inspect_model | 包读取源、限制 -> 格式/算子需求/内存估算 | 检查版本与必要元数据；不启动设备 |
| load_model | 包、平台读取服务、预算 -> 只读模型对象 | 权重、tokenizer、配置来源一致；失败无有效对象 |
| create_session | 模型、上下文限制、内存预算、后端策略 -> 会话 | 工作区/持久状态归会话，模型归调用方 |
| prefill | 会话、token IDs -> next_logits | 消费整个输入，缓存长度与已消费位置一致 |
| step | 会话、一个 token -> next_logits | 恰好消费一次；生成策略选 token 不更新模型状态 |
| reset_session | 空闲会话 -> 初始状态 | 清空有效状态，保留模型和已分配资源 |
| destroy_session | 无在途任务的会话 -> 已释放 | 先 drain/quiesce，不能只依赖 wait 超时 |

高层生成器记录待消费 token。EOS/长度上限/取消/错误是独立停止原因。
token 解码器负责 UTF-8 跨 token 缓冲；具体 tokenizer、采样和缓存布局待模型确定。
首版单模型、单活动会话、单在途任务；不承诺支持任意网络架构。
A5 的 load_model/create_session 只实现静态算子包与同步 run 子集，
不等同于上述 token/prefill/step 接口；其参数和生命周期以 model_package.md 为准。

## 算子与后端接口（契约，A6 已实现模拟子集）

- query_support：接收算子名、形状、dtype/layout、属性和内存域，返回支持或原因。
- execute/submit：接收算子描述和已绑定张量，返回同步结果或唯一任务 handle。
  完整合法性检查在副作用前完成；提交被拒绝时不取得缓冲区所有权。
- poll/wait：返回 pending 或已完成结果。TIMEOUT 是等待结果，不是任务终态。
- cancel：先返回请求状态；直到设备确认停止，缓冲区仍在途。
- completion：成功才使输出有效；失败/取消完成也必须明确设备已静止。
  无法确认静止时隔离相应缓冲，交给设备恢复流程。
- release：只释放已完成/已静止的任务 handle；不能释放 pending 任务。

结果只在成功完成并完成设备可见性同步后可读。
非一致性 DMA 的 cache clean/invalidate 由平台/驱动实现，不能用普通 FENCE 替代。
软件回退须由显式策略允许，并记录实际后端，禁止暗中改为主机推理。
目前提供同步 Python 软件参考、A4 PC C 后端及 A6 逻辑时钟模拟设备。
A6 的 submit 采用私有输入快照及会话 arena lease；不模拟真实 DMA/cache，
完整接口和状态确认语义见 sim_device.md。实际设备路径仍未实现。

## 平台服务（S3 已实现 PC 子集，板端仍为设计）

读取服务提供 read_at(offset, length)，检查短读/范围并返回明确错误。
内存服务提供带 alignment/内存域的申请与释放；时间源单调且标明单位。
设备服务提供搬运、同步、完成和错误；请求与结果使用任务标识关联。
应用不访问寄存器，模型适配器不访问 UART。现有 UART 仅作为调试读回。
真实 CPU 可读结果、DDR、DMA、MMIO 桥接均是后续集成项。

## 本轮可执行子集

TensorSpec(dtype, shape, storage_shape, layout="row_major")：
float32/int32、1—4 维、连续行优先；单张量最多 1,048,576 个存储元素。
该限制适用于阶段 1A 工具，不代表最终模型限制。

reference.execute / oracle.execute：
- linear：weight[N,K]、input[K]、可选 bias[N] -> [N]，无转置、无广播。
- add：a、b 的形状和 dtype 完全相同 -> 同形状。
- relu：input -> 同形状，逐元素 max(x,0)。
- 输入必须有限且同类型。FP32 已存储值提升到 FP64，标量路径用 math.fsum，
  NumPy 路径用 FP64 矩阵乘；输出舍入到 FP32。
- INT32 使用无限精度中间值，仅最终输出检查 INT32 范围；无饱和/回绕。
  中间项超过 INT32 后抵消仍合法，此规范不假定未来硬件累加器已经支持。
- 非有限输入拒绝；无法产生有限 FP32 或合法 INT32 输出时返回 NUMERIC_OVERFLOW。

compare_arrays(expected, actual, atol=1e-6, rtol=1e-5)：
形状/dtype 相同；整数逐元素精确；浮点逐元素满足
abs(actual-reference) <= atol + rtol*abs(reference)。
NaN/Infinity 永远不通过；零参考值不计算相对误差，缺失指标为 JSON null。
报告包含 passed、误差、数量和首个不一致坐标；不把相似度当成通过条件。
直接比较允许零维 ndarray：失败 first_mismatch=[]，成功为 null；
其他维度使用首个行优先坐标列表。此比较器规则不放宽 TensorSpec/fixture/模型包的 rank 限制。
这些小型基础样本门槛不自动适用于真实模型、量化或长向量数值验收。
