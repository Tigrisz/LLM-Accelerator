# 候选模型内存需求采集与核算（S6 v1）

没有候选图、shape profile或目标内存图时，本表保留未知，不能给“模型能装下”的结论。
以下按当前0.6.0规划器、T3 native ABI2和S5受管载荷口径，另列未纳入的真实PC/目标开销。

## 每个profile必须采集

| 项目 | 必填字段 | 核算依据 |
|---|---|---|
| 源模型/包 | 文件实际长度、sha、压缩/packing、转换峰值、manifest | 源字节不等于目标arena；原Python包与weights副本在S5预算外 |
| 权重 | 每tensor逻辑/物理shape、编码、scale/zp与共享关系、目标对齐 | 先算物理载荷，再对每个实际分配/分片对齐 |
| 激活 | 每节点输入/输出的物理字节、producer/last consumer、图分支/所有输出 | 用完整图的闭区间寿命求峰值，不能只看最大单个tensor |
| workspace | 每算子/后端/profile的需求与对齐、同步并发使用关系 | 当前max(logical_output_elements*4)后对齐；新算子不能沿用此公式 |
| 持久状态 | 是否存在、维度/dtype/packing、最大容量、增长/reset规则、每Session/共享所有权 | 当前没有状态池；不存在时以证据确认false，未知不能当0 |
| C元数据/栈 | 实际ABI的sizeof、图规模、描述长度、prepare栈工作集、线程/中断栈 | 查实际构建；不同平台不复制x86_64大小 |
| 追踪/profile | event/byte预算、是否共享ledger、profile表大小、导出峰值 | 最大预留和实际驻留分别列；缓存到close才释放 |
| 任务 | 输入快照/最大逻辑输出、max inflight、终态未release、隔离与history cap | 每个已接收任务保持预留到release，失败/取消也不提前释放 |
| 额外开销 | loader原包、转换、调用方副本、堆头/碎片/容器、libc/共享库、线程栈、驱动 | 不在S5载荷账本中也需纳入系统总可用内存验收 |
| 目标分区 | ROM/片上RAM/DDR/设备可达域、地址范围、对齐、保留区、搬运与一致性 | 分域分别验证容量和可达性；总字节相加不能证明DMA可访问 |

## 当前未量化子集的计算

定义 `align(n,A)=ceil(n/A)*A`，当前存储dtype每元素4字节。

- tensor物理载荷 `P_t=4*product(storage_shape_t)`；不能用logical_shape代替含padding的大小。
- 权重arena `W=sum(align(P_t,A))`，同一模型的Session共享W；多个模型实例各自分配。
- 激活arena `A_live` 使用plan_memory实际结果。当前仅shape==storage_shape的槽位可复用，
  两张量寿命必须严格分离（previous.last_use < next.first_use）；同节点输入/输出不能共用槽。
- workspace arena `S=align(max_node(4*product(logical_output_shape)),A)`。
- 每个非零arena的PC backing是`arena_bytes+(A-1)`；零载荷不加该对齐字节。
  `MemoryPlan.total_bytes=W+A_live+S+相应对齐预留`只描述单模型/单Session的arena方案。
- N个同时存在Session：权重backing只加一次，activations/workspace backing各加N份。
  model.plan.total_bytes不能直接乘N，否则重复计算共享权重，同时还会漏掉C/trace/task等资源。

原C后端每Session原生元数据：

```text
NT*sizeof(ir_tensor) + NN*sizeof(ir_call) + sizeof(uint32_t completed)
optional_profiles = NN*sizeof(ir_node_profile)
```

S4静态C适配每Session另有：

```text
execution_image = 64 + 96*NT + 24*NN   # 磁盘字节，无指针/原生struct填充
ctypes_image = execution_image + 1     # 当前适配器的终止字节，不适用于独立host分配方式
sizeof(irs_context) + NT*sizeof(ir_tensor) + NN*sizeof(ir_call) + NT  # 常驻tensor_state
optional_profiles = NN*sizeof(ir_node_profile)
prepare_inspect_working_set = irs_inspect_workspace_bytes(NT)  # 4*NT，caller-owned临时区
```

S4的completed计数在context内，不再加原C后端的单独uint32。
T3检查工作区按4*NT实际分配并计账，bind返回释放，不再有32768字节固定局部数组预留；不能同时当常驻与瞬时重复加总。
可选profile必须在必需绑定工作集预留后准入；不足时禁用观察并标记不完整，不应挤掉必需预算。

当前模拟任务每个预留：`sum(input logical ndarray.nbytes)+sum(output logical elements*4)`。
任务输出是逻辑副本，不能套用C arena的storage字节；resident随输入/输出实际持有变化，预留保持到release。
task/session/event对象用数量上限约束，不估算成任意字节。S5 ledger的peak是同时存活预留峰值，
不能把各类别发生在不同时间的peak简单相加称为实测总峰值。

## 量化需求尚未确定时

只有编码/packing粒度确定后才计算；以下是条件公式，不是当前执行支持：

- 无行/组对齐的连续b位payload：`ceil(physical_elements*b/8)`。
- 每行独立字节对齐的R行×Kp：`R*ceil(Kp*b/8)`，与前式可能不同。
- 分组/tiling/尾组另加声明的padding、头部和分片对齐；scale/zp按其实际tensor物理shape与dtype计量。
- 反量化/重排到FP32若被明确选择，要同时计原压缩数据、输出权重与转换workspace的重叠峰值、
  加载时间及数值变化；不能拿源权重位宽估算已转换的arena。
- 非对称格式的数值零可能需要非零编码；当前writer默认零字节初始化不能直接套用。
  现有未量化读入/执行检查数值零，FP32的±0均接受，不能把默认写法误当作只准许全零字节。

若且仅若候选具有同shape、同dtype的K/V缓存，可用
`2*layers*batch*max_positions*kv_heads*head_dim*bytes_per_element`作为未压缩payload项；
它不含对齐、scale/zp、状态索引/分页、临时搬运，也不适用于任意状态结构。
没有这种缓存的模型无需该项；存在时当前框架需先实现状态协议与验收。

## 准入判断

逐profile执行严格包检查→plan→后端query→目标地址/size_t范围→C bind→共享账本实测。
分别报告加载/prepare峰值、稳定运行峰值、最大并发、终态未release和未知隔离峰值，以及确认关闭后的余额。
总预算、分类预算、记录数量、每内存域容量都要满足；板端还需实际地址映射和同步验证。
PC默认64MiB、模型参数量、单次arena峰值或32位数学检查，任何一项单独都不能证明目标模型可运行。
