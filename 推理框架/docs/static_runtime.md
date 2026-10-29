# S4 纯 C 静态运行时

当前工具0.6.0；T3纯C native运行时ABI2，inspect/bind改用_v2与调用方state/检查区，旧二进制须重编译，见[t3_metadata.md](t3_metadata.md)。static image v1 / C平台与后端回调API1保持。
S5资源账本见resources.md；C PC服务irs_pc/irs_block具体结构为services ABI2，调用方须重编译。
原模型包、Python 平台/后端 API、ir_core ABI 和追踪格式仍为 1。

## 执行路径

PC 的 `export-static` 使用原模型包校验器、S3 平台读取和静态内存规划器：
检查 JSON/权重 SHA256、形状/图拓扑、支持集和预算，然后导出
`execution.bin`、重排后的 `weights.bin`、供人/离线工具使用的 `export.json`。
C 运行时不读取 JSON，不加载 Python，不识别模型名称。

`irs_read_info` -> 调用方供应实际容量的检查区 -> `irs_inspect_v2` -> arena/元数据/state -> `irs_bind_v2` -> 释放检查区 -> `irs_input`
-> `irs_run` -> `irs_output` -> `irs_close`。
绑定后运行不分配堆内存；context、tensor/call/profile 表、三个 arena 都由调用方持有。
元数据也占内存：T3 context只保留指针/运行状态，T字节tensor_state常驻；4T字节检查区借用至bind返回后释放。
不宣称已满足目标栈预算；PC host/绑定显式分配并按c_metadata计账，受管载荷非RSS。

输入/输出文件按 tensor 表中 input/output 角色的出现顺序拼接**物理 storage_shape**字节，
小端 FP32/INT32，每元素4字节；输入 padding 必须0，所有浮点输入与常量必须有限。
每次 run 都须重新提供全部输入，因为激活复用可能覆盖旧输入。输出仅成功且完成 acquire 后可取得。
独立程序的输入/输出与模型包中 inputs/outputs 列表排序不必相同，以 tensor 表为准。

## 描述布局

全为小端整数，无原生指针、无编译器 struct 填充。header64 + tensor_count*96 + node_count*24，禁止尾部数据。

| 位置 | 字段 |
|---|---|
| header 0 | 8字节 IRS4BIN1 |
| 8..31 | u32 version=1、endian=0x01020304、tensor_count、node_count、alignment、reserved=0 |
| 32..55 | u64 weights/activations/workspace 容量 |
| 56..63 | u32 描述 CRC32（跳过56..63）、权重 arena CRC32 |
| tensor 0..15 | u32 dtype(1FP32/2INT32)、rank、role(0constant/1input/2intermediate/3output)、arena(0weights/1activations) |
| tensor 16..31 | u64 offset、物理 byte_length |
| tensor 32..95 | u64 shape[4]、storage_shape[4]；闲置维度0 |
| node 0..23 | u32 op(1linear/2add/3relu)、a、b、bias、output 的tensor索引、reserved=0；缺失输入0xffffffff |

CRC用于发现偶发损坏，不能认证来源。SHA256来源与导出指纹在离线sidecar/验收清单中保留。
C 仍检查数量、长度、维度、布局、闭区间生命期与复用冲突、writer唯一/引用先后、
arena偏移/对齐/实际地址跨度、元数据/arena/描述/服务表别名和 ir_query。
描述和服务表仅绑定时借用；context复制服务表，绑定后不允许调用方修改tensor/call表。
context第一次使用必须零初始化；关闭后可重绑，执行中/未知/已绑定时不可覆盖绑定。

## 平台和后端

`ir_pc.h`：`irs_reader/read_exact` 使用单次size快照，短读直接报错；
`irs_pc_read` 普通文件、前后大小核对、限长与关闭；没有并发修改文件的事务快照保证。
`irs_pc_alloc/free` 对齐4..4096、size_t/u64防溢出、预算、失败注入与所有者检查；
block须零初始化、只转移所有权而不可复制后分别释放；alloc/read拒绝覆盖非空block并保留旧资源。
`irs_check_span(...,32)` 允许最后一个字节0xffffffff，拒绝4GiB长度或地址截断。
默认C时钟 Linux CLOCK_MONOTONIC / Windows QueryPerformanceCounter；节点另用原core process CPU clock。
host-coherent同步只代表当前PC同线程缓冲区可见性，未实现DMA/cache维护/FENCE。

`irs_backend` query/execute/recover 接受静态整链，不自动回退；默认使用原 ir_core。
`execute` 必须明确 completed 和 quiescent；未知或畸形结果进入隔离状态。
同步任何失败同样隔离，禁止 run/output/close，需所有未知服务 recover 确认后方可复用/关闭。
调用方必须持有全部 arena；未知状态不能自行 free。PC host 失败时保留到进程退出，
这不构成真实硬件停止访问的证明。

`CStaticRuntimeBackend` 接入S2选择/显式回退策略，prepare通过同一二进制描述绑定S3既有arena；
Session负责外层S3同步/隔离，C侧在此适配模式使用默认同线程同步。SimDevice生命周期不变。
适配模式输出与独立C进程做逐字节对照，原TraceRecorder继续关联model/session/task和C节点。

## 独立追踪

PC host 导出 `inference-c-static-trace/version1`，与原Python运行时追踪是两种格式。
包含绑定、run begin/end、publish/acquire、chain进度、逐节点CPU profile和资源余额；不保存数值。
时钟不可用/反转或观察写失败不能虚构时长；观察故障不更改数值执行状态。
`validate_c_trace` 用于成功执行验收：完整生命周期顺序、进度、全部节点、时间域与资源归零。
失败执行保留错误状态/已完成前缀及未运行节点；不通过成功验收器，不发布数值输出。

## 复现

在本目录的WSL/Linux（gcc、Python+NumPy）运行：

```text
python3 -B -m inference_ref export-static --package build/my_package --output build/my_static
python3 -B -m inference_ref verify-static --fixtures fixtures/synthetic-v1 --output build/s4_new
IR_REQUIRE_C=1 python3 -B -m unittest discover -s tests -v
```

独立程序仅链接C标准库和libm；可在没有Python的PATH运行：

```text
/absolute/ir_static_host execution.bin weights.bin inputs.bin outputs.bin trace.json
```

输出/追踪拒绝覆盖已有路径；输出写入/关闭失败清理本次创建的部分数值文件，未取得所有权的路径不删除。
部署需要同时携带执行描述和权重，不需要export.json、Python或NumPy。
PC验证不等于RV32编译/执行、板上验证或实际模型推理；当前仍为静态小算子支持集。
