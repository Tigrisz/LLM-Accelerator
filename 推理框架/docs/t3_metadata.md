# T3 纯 C 元数据与栈优化

运行时0.6.0，纯C native ABI2；ir_core ABI1、IRS4BIN1磁盘v1、平台/后端函数表API1、PC services ABI2保持。仅PC验证，不绑定模型/W4A8。目标工具链/布局/栈峰值仍未知。

## 容量与工作区归属

保留4096张量、1024节点上限和原算子限制；调用方可提供更小实际容量，不足返回RESOURCE_LIMIT，不截断。

| 对象 | 计算和归属 | 生命周期 |
| --- | --- | --- |
| irs_context | sizeof查询；不再有按4096展开的数组，也无共享全局scratch | 调用方提供、首次全零；close成功后可复用 |
| tensor_state | T字节，角色bit0..1、输入已供应bit2，内部字节不可由调用方直接修改 | bind到close成功，未知执行/同步继续保留 |
| irs_lifetime检查区 | 4T字节，两个int16，按_Alignof(irs_lifetime)对齐；[-2,1024]含所有哨兵/索引 | 仅inspect/bind期间借用；返回后可释放/覆盖，run不访问 |
| tensor/call表 | T*sizeof(ir_tensor)、N*sizeof(ir_call) | 同state；按本机ABI重编译 |
| 可选profile | N*sizeof(ir_node_profile) | 必需资源先取得，可选资源不足只影响观测 |
| arena | 原权重/激活/数值workspace与对齐规划 | 不与上述区域/镜像/服务结构相交，未知继续保留 |

最大检查区16KiB，位于调用方内存，不再是runtime局部数组。9张量四节点链的检查区36字节、状态9字节；context不再承担T2固定20KiB角色/供应数组。
图像大小仍64+96T+24N字节。tensor/call/state/inspect等元数据capacity仅检查和使用必需前缀；前缀须有正确地址范围、类型对齐且不重叠，多余元数据尾部不使用。
arena按调用方声明的weights/activations/workspace完整字节跨度检查，包括未使用尾部；整段保持独占，尾部也不能与其他区重叠。此保守行为保持原实现。
不提供跨任意context的全局地址注册，调用方负责不同会话的持久存储不重叠。同一检查区可串行复用，不可重入共享。
检查区与数值workspace在同次bind中仍必须独立，避免检查尚未完成就破坏arena；本次不自动复用二者。

## ABI2接口与迁移

1. irs_runtime_abi_version必须为2；函数表api_version仍为1。
2. irs_read_info(image,size,address_bits,&info)检查header/版本/长度/CRC/容量/可表示arena长度，供分配查询；不代表图语义已验收。
3. irs_inspect_workspace_bytes(T)、irs_tensor_state_bytes(T)查询字节数；T=0或>4096返回0，不代表零张量合法。
4. irs_inspect_v2增加inspect地址/字节数，执行完整图序、张量定义/使用、闭生命周期和arena别名检查；info仅成功写回。
5. irs_bind_v2在原arena/tensor/call/profile参数后增加state+capacity、inspect+bytes，再接平台/后端。先查全部使用区域与服务结构的边界/别名，再写工作区/context；绑定时再完整检查。
6. irs_tensor_role取代ctx.roles直接访问，非法状态/索引返回UINT32_MAX。
7. input→run→output→close保持原语义；run消耗本次供应标记，数值失败保留完成前缀；未知禁止有效输出和close，确认recover后才能释放。

运行时无malloc/全局scratch，run阶段无分配；所有缓冲由调用方持有。镜像、描述符、状态和服务结构是受信对象，检查/执行期间不能并发修改，本次不增加线程调度器或恶意驱动隔离。

ABI2不兼容旧context和inspect/bind签名：旧irs_inspect/irs_bind符号不再导出，以_v2命名，避免旧二进制调用新签名损坏内存。
原生调用方须重编译、提供两个缓冲并迁移函数；ctypes设置新调用签名前查询ABI，缺版本函数或版本!=2即拒绝并要求重建。C数值核心仍可按ABI1独立使用。
旧模型包/IRS4BIN1无需重导出，54冻结样本、原174 Python测试源保持；变化仅为本机运行时布局/调用。

## PC资源与失败

context/state/检查区/tensor/call归c_metadata，profile单列；不再把检查区伪计成固定stack reservation。绑定后释放4T检查区，准备峰值含它，常驻量不含。
必需资源先分配，再尝试profile；失败回滚已取得的资源，未知保留state/arena。PC资源账本仍是受管载荷，不是RSS，也不覆盖全部Python包装/线程栈。
host仅profile返回RESOURCE_LIMIT时以NULL profiles继续；顶层profile_available=false/profile_status=RESOURCE_LIMIT，complete=false，但计算成功仍返回status=0并写有效输出。非资源类配置错误仍中止，不伪装观测可用。
host trace事件不变，resources增加runtime_abi/context_bytes/tensor_state_bytes/inspect_workspace_bytes；旧inspect_stack_reserved_bytes显式0，仅表示去掉固定数组预留，不代表整个栈为0。

## 验证范围

新增T3工具/native用例单列，覆盖容量/别名、独立context、供应标记、未知恢复、4096张量/1024节点实际C执行、free检查区后run、旧ABI拒绝和无分配器/旧入口符号；普通与sanitizer路径都测。
同编译参数比较T2固定源码与当前源码的sizeof和ir_static.c各函数GCC .su，不含ir_core等模块完整调用图。结果不是调用链/ISR峰值或运行高水位，PC运行峰值也留null。
入口（Linux/WSL，Python、gcc/nm）：`python3 -B tools/audit_static_metadata.py --output build/t3_metadata_new`；输出目录必须不存在。
统一reproduce干净副本入口增加此审计与T2历史来源核对，保留174/样本/双链/压力/S6路径。

T2当时9份框架源按原SHA保存在target_platform_sources/framework_t2，当前T2来源索引指向这些历史快照；原T2 build证据/收据不改。T2的32KiB/20KiB记录不是当前占用。
目标交叉编译器/库、RV32 sizeof/offsetof、链接map、实际可用余量、任务/ISR峰值仍未知，六类目标预算不因PC优化而填数。仍需目标工具链、map/.su/调用图及仿真/实板高水位才能判断TCM适配。
正式数据见[t3_validation_report.md](t3_validation_report.md)。
