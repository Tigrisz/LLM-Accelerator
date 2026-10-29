# A5：模型包、静态内存规划与 PC 会话

当前工具0.6.0；model-package-v1仍为version1，ir_core ABI1；S4离线导出见static_runtime.md，S5受管预算口径见resources.md。
S3 read_package/inspect_model/load_model/create_session 支持 platform；模型 close/共享借用见 platform.md。
S2 通用整链后端/显式选择见 backends.md；trace 参数与会话追踪补充见 tracing.md。

实现范围：模型无关的数据包和静态顺序 DAG；Python 负责包检查与内存规划，
默认 C11 后端负责全部算子数值计算，也可显式绑定 S2 StaticBackend。不包含模型名称判断、W4A8、tokenizer、KV Cache、
动态形状、量化算子、设备驱动或板端 C 文件解析器。

## model-package-v1

一个目录，固定读取 manifest.json 和 weights.bin。其他文件不参与执行，不加载代码。
两文件必须是普通文件，禁止符号链接，清单不允许指定其他权重路径。
JSON 为 UTF-8，禁止重复键、NaN/Infinity、未知字段和隐式版本转换。

清单字段均必需：

| 字段 | 约束 |
| --- | --- |
| format / version | inference-model-package / 整数 1，bool 不算整数 |
| model_id | 英文字母/下划线开头，后续字母数字、下划线、点、短横线，长度 1..64 |
| tensors | 1..4096 个张量记录，ID 唯一 |
| nodes | 1..1024 个节点，节点 ID 唯一，预先按拓扑顺序排列 |
| inputs / outputs | 非空、唯一的张量 ID 列表，须与相应角色完全一致 |
| weights | file 固定 weights.bin；byte_length、sha256 校验整个文件 |

张量记录：id、role、dtype、layout、shape、storage_shape。
role 为 input、constant、intermediate、output；常量还必须有 blob。
blob 含 offset、length、sha256；非常量禁止 blob。
dtype 当前支持 float32/int32，layout 为 row_major，rank 1..4，尺寸为正整数。
shape 不大于 storage_shape，单张量存储元素最多 1,048,576。
清单最多 1MiB，weights.bin 最多 16MiB；属于工具限制，不是最终模型容量。

常量是小端、行优先的整个 storage_shape，length 必须等于存储元素数 * 4。
blob 按文件偏移排序后，第一段从 0 开始，后续段恰好接在上一段尾部向 64 字节上取整处；
对齐空隙必须全零，禁止重叠、尾部多余数据及 uint64 越界。空常量集合使用空 weights.bin。
同时校验整体和每段 SHA256；哈希用于内容一致性，不提供签名认证。
物理存储内所有 FP32 值必须有限，逻辑区域之外的 padding 必须为数值零。

节点记录：id、op、inputs（算子参数名到张量 ID 的映射）、output（一个张量 ID）。

| op | inputs | 形状 |
| --- | --- | --- |
| linear | weight、input，可选 bias | W[N,K]、x[K]、bias[N] -> [N] |
| add | a、b | 完全同形状 -> 同形状 |
| relu | input | 同形状 -> 同形状 |

同一节点全部输入输出 dtype 相同，不广播、不转换精度。
input/constant 初始可读且不能作为节点输出；intermediate/output 恰好写入一次。
不能向前引用、环回或重写；每个声明张量都必须实际使用或作为最终输出。
output 可以继续被后续节点读取，但其内容必须保留至链尾。
格式版本允许未来扩展；当前不认识的算子、dtype/layout 明确 UNSUPPORTED，
未定义字段如量化描述不能被悄悄忽略。

## 接口

| Python API | 行为 |
| --- | --- |
| write_package(path, model_id=..., tensors=..., nodes=..., inputs=..., outputs=..., constants=...) | 离线写入不存在的新目录；常量参数为精确逻辑形状、原生 dtype ndarray，自动补零并转小端 |
| read_package(path) | 完整检查文件、常量和图，返回 frozen ModelPackage，常量 bytes/视图只读 |
| inspect_model(path, memory_budget=...) | 完整验证并返回模型需求、哈希及计划，不分配运行时 arena、不启动 C 计算 |
| plan_memory(package, memory_budget=..., alignment=64) | 对已验证包计算不可变 MemoryPlan，含每张量偏移、容量和生命周期 |
| load_model(path, memory_budget=..., trace=None) | 检查预算后分配共享权重 arena，返回 LoadedModel；可关联 A7 追踪 |
| create_session(model, backend=None, registry=None, policy=None, memory_budget=..., trace=None) | 整链能力选择先于会话 arena；按 plan 绑定选定后端；默认继承模型 recorder |
| session.run(feeds) | 按清单精确输入键/形状/dtype，单次 ir_execute_chain；成功返回输出副本 |
| session.last_result | 状态和 completed_steps 的副本；失败不返回有效输出 |
| session.execution_id | 实际进入 run 时递增的只读标识，供 A6 区分本次进度与历史记录 |
| session.memory_info() | arena 地址和实际 NumPy backing 大小，可检查复用及重复运行稳定性 |
| session.close() / with session | 释放会话持有的缓冲区/引用；close 幂等，关闭后不能再运行 |
| session.recover() | S2 未知执行异常后取得后端静止确认；确认前禁止重跑/关闭，不重选后端 |

状态沿用 ContractError.code，新增 INVALID_MODEL、INVALID_STATE；
其他包括 UNSUPPORTED、INVALID_SHAPE、CHECKSUM_MISMATCH、RESOURCE_LIMIT、
NONFINITE、NUMERIC_OVERFLOW、IO_ERROR、ALREADY_EXISTS、BUSY。
加载失败不返回部分模型；输出目录冲突拒绝覆盖。写包中断可能留下不完整目录，
读取时会拒绝，不承诺发布过程的目录级原子性。

LoadedModel 和 ModelPackage 中的文件数据/计划不可变，权重跨会话共享；
Python 对象及内部指针属于受信调用方接口，不用于隔离恶意进程内内存写入。
调用方须串行使用单个会话、保持 feeds 在同步调用结束前不变。
BUSY 检查防止明显的重入，不是跨线程调度器。无在途异步设备任务。

## 内存规划

默认预算为 64MiB，预算可显式修改；alignment 为 4..4096 的 2 次幂，运行时默认 64。
三个独立 arena：共享 weights、每会话 activations、每会话 workspace。
workspace 是全部节点最大逻辑输出字节数上取整，整条同步链复用同一区间。

激活使用闭区间 [生产节点, 最后消费者]；输入从 -1 起有效，最终输出保留到节点数 N。
按首次产生顺序进行 first-fit 槽复用：只有前一张量 last_use < 下一张量 first_use 才可复用，
因此同节点读/写不重叠。槽不拆分，不声称全局最优；offset、reserved_bytes 和存活范围均报告。
带 padding 的张量分配独立槽，不参与复用，保证输出 padding 不会继承别的张量逻辑数据。
每次 run 清零激活 arena，再复制全部输入；每节点输出由 C 暂存到 scratch 后提交。

total_bytes 计入三个 arena 容量以及各非空 arena 的 alignment-1 字节 backing 额外空间。
预算在申请 arena 前检查；实际 backing nbytes 与计划一致。预算计算为“共享模型 + 一个会话”，
不是多个同时存活会话的全局限额。它不包含 Python/NumPy 对象、保留的包文件 bytes、
C 调用描述符、输入、返回副本、参考计算及编译工具的进程内存。
unpooled_bytes 表示同样对齐/同一共享 scratch 但不复用激活槽的对照值。

执行时不会为每个节点重新分配张量或 scratch；准备的 C 描述符直接指向 arena。
运行前检查输入，任何失败都不返回有效输出，last_result 记录失败状态与 C 完成节点数。
先前成功节点在当前 arena 中可能已提交；不承诺整图事务回滚。
下一次 run 重新初始化激活，可在纠正输入后重试，无持久状态需要恢复。

## 复现

在 WSL/Linux 的本目录：

    IR_REQUIRE_C=1 python3 -m unittest discover -s tests -v
    python3 -m inference_ref verify-packages --fixtures fixtures/synthetic-v1 --output build/a5_run_new
    python3 -m inference_ref inspect-model --package build/a5_run_new/chains/int32

Windows PowerShell：

    wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec env IR_REQUIRE_C=1 python3 -m unittest discover -s tests -v
    wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec python3 -m inference_ref verify-packages --fixtures fixtures/synthetic-v1 --output build/a5_run_new

verify-packages 会把原 54 个样本转换成不含 expected 的数据包，再真正加载、规划和运行 C，
逐样本对齐 stored expected / scalar / NumPy。另执行 FP32/INT32 四节点包及重复运行，
记录计划、预算、复用、文件/源码/二进制哈希和原生 C sanitizer 证据。
退出码：0 通过；1 验收数值或原生 C 测试失败；2 参数、模型包、工具或输出冲突。
inspect-model 不需要编译器；完整验收需要 A4 相同的 C/NumPy 环境。

程序接入时先通过 c_backend.build_backend / CBackend 得到后端，load_model 得到模型，
with create_session(model, backend) as session 后调用 session.run({输入ID: ndarray})。
后续模型适配器只需生成受支持的静态包；新增算子/量化/动态状态须另行定义版本和验收。
