# 当前框架能力矩阵（S6资料 v1）

T8提供当前版本统一干净副本验收入口，覆盖既有54样本和两条原四节点链；仅整合和核验既有能力，不新增算子/dtype/量化或实板支持。实际验收结果与状态边界见[t8_validation_report.md](t8_validation_report.md)。

算子/格式能力基于S6核对并保持；当前运行时0.6.0/native ABI2，元数据/栈变化见t3_metadata.md。T4指定INT32链、T5/T6原27 INT32/27 FP32样本、T7原FP32/INT32四节点链的RV32范围分别见各期验证报告；均不代表任意模型或实板已验证。
支持条件必须同时成立；能力可query不等于已验证任意形状、任意模型或目标板。

| 维度 | 已实现及约束 | 不支持/未验证边界 | 主要依据 |
|---|---|---|---|
| 算子 | linear W[N,K]×x[K]，可选bias[N]；add同shape/dtype；relu逐元素 | 无batch矩阵乘/转置/广播/可配置属性/任意融合；其他算子未实现 | inference_ref/contracts.py、c_execution.py、c/src/ir_core.c |
| 图执行 | 自有静态DAG、按已排序节点顺序整链；多输入/多输出、共享只读常量、临时激活复用 | 不提供动态控制流、动态shape、持久状态或自动切图；分支应写为显式拓扑数据依赖 | model_package.py、memory.py、runtime.py |
| dtype | float32/int32存储，节点输入/输出同dtype；不同独立节点可有不同dtype，不能隐式跨类型连边 | 无FP16/BF16/INT8/packed低位/FP8；无cast或混合精度算子 | TensorSpec、CStaticBackend.query、ir_query |
| FP数值 | 已存FP32提升FP64；C用有界展开累加，Python标量math.fsum；末端舍入FP32，拒绝非有限/溢出；T6以libgcc软浮点验证受测RV32子集 | 不是硬件FP32逐次MAC或任意模型精度承诺；无完整IEEE754/动态舍入模式证明；不能由存储dtype推断计算语义 | reference.py、oracle.py、ir_core.c、docs/c_backend.md、t6_validation_report.md |
| 整数数值 | 原始INT32，乘加精确中间值，最终INT32范围检查，无饱和/回绕；C在支持上界内用宽和表示 | 不是INT32累加器硬件模型，也不是量化算子；无scale/zp/requant/饱和规则 | contracts.py、ir_core.c wide_sum |
| 量化 | 需求契约有说明，执行/模型包/ABI没有量化参数结构 | 所有量化编码和转换均须扩展；普通INT32输入不构成量化支持 | docs/contracts.md、TensorSpec/ir_tensor/模型包字段 |
| 张量 | 连续行优先，逻辑shape与storage_shape分离，rank1..4，各维正整数；padding须为数值0，FP32的±0均接受；writer/激活初始化默认写零字节 | 无任意stride、view/transpose/tile、量化zero-point padding协议、符号维度、scalar或空维张量 | contracts.py、model_package.py、ir_static.c |
| 单张量 | 最多1,048,576个**存储元素**；当前每元素4字节，即最多4MiB物理载荷 | 是本阶段工具/C支持限制，非比赛或未来模型上限 | MAX_ELEMENTS、IR_MAX_ELEMENTS |
| 包大小 | manifest≤1MiB，原weights.bin≤16MiB，tensor≤4096，node≤1024；常量blob按64字节对齐；严格字段与SHA256 | 不直接加载ONNX/TFLite/PyTorch/GGUF/safetensors等外部格式；需单独转换 | model_package.py常量/_validate |
| 内存规划 | weights共享；每Session activations/workspace；默认64字节对齐；可选4..4096二次幂；闭区间寿命，不做输入/输出原地重叠 | 无KV/循环状态池、设备地址规划、流式加载/权重分片；带padding激活不复用槽位 | memory.py、runtime.py、ir_query |
| 预算 | 旧MemoryPlan默认64MiB含arena对齐预留；S5共享账本另计C/trace/task等，分类/总预算可配置 | 64MiB是PC默认策略；不等于板端可用RAM，不含全部RSS/加载器/调用方副本 | memory.py、resources.py、docs/resources.md |
| C元数据 | ctypes按本机sizeof计量；执行描述/context/T字节state常驻；4T字节检查区临时借用；profile可选 | native ABI2需重编译；PC sizeof/frame不能照搬RV32，线程栈峰值另测 | static_backend.py、ir_static.h、t3_metadata.md |
| 后端 | pc_c / pc_c_static与可替换整链接口；仅显式allow_fallback且query明确不支持才按列表回退 | 无执行失败后重跑、静默精度改变、自动异构分区；实际硬件后端未实现 | backend.py、c_execution.py、static_backend.py |
| 模拟任务 | 单owner线程协作式FIFO；私有输入快照、完成可见性、取消/隔离/确认恢复、lease | 不是真实异步DMA或硬件抢占；max_tasks/max_sessions默认各16，可配置1..1024 | sim_device.py、docs/sim_device.md |
| S5资源 | arena/C metadata/profile/trace载荷、任务staging与record/event数；峰值/预算/失败回滚；未知整图保留 | 不是RSS；原Python包和weights、容器/包装器、libc、调用方副本等需额外测量 | resources.md、s5_validation_report.md |
| 追踪 | 既有模型/会话/节点/任务与平台关联；host时间/C进程CPU/逻辑tick分离；缓存有界、关闭释放 | 不是板端耗时/总内存测量；观察不完整不能发布完整性能结论 | tracing.py、docs/tracing.md |
| 纯C部署 | PC离线包检查/规划→无指针IRS4BIN1/权重→C绑定arena/run；运行不依赖Python；T5/T6单节点样本、T7原两类型四节点链分别有RV32仿真范围 | 不证明任意FP32图/模型/动态状态；无目标JSON导入器或实板；按节点提交与arena复用，不提供整链回滚；CRC不认证来源 | static_export.py、ir_static_host.c、各期历史报告、t7_validation_report.md |
| ABI/格式 | ir_core ABI1、平台/后端回调表1、资源API1/磁盘1；native运行时ABI2，PC服务结构ABI2 | inspect/bind用_v2，context及调用方重编译，旧库拒绝 | ir_core.h、ir_pc.h、ir_static.h |

没有列出的外部算子、dtype、布局或状态协议一律不能由“可替换后端”推断为已支持。
原54样本/双链和S5压力仅覆盖既有子集；候选模型仍需自己的golden、质量和资源验收。
