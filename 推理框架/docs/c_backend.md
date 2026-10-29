# A4：PC 最小 C 算子后端与调用链

当前工具0.6.0，ir_core ABI1不变。S5元数据/预算见resources.md，S3平台见platform.md，S4纯C见static_runtime.md；C数值核心未改。
A7 可选逐节点 profile 扩展见 tracing.md；
S2 CStaticBackend/CBoundChain 适配见 backends.md。本页描述 A4 数值层，图会话由 A5 提供。

当前实现：同步 C11 CPU 后端，执行 float32/int32 的 linear、add、relu；
固定样本由 Python 校验，C 执行数值计算，Python 用三个参考分别判定。
不接入模型、W4A8、DDR、MMIO、FPGA，也不构建完整图执行器。

## 层次

- c/include/ir_core.h：原生进程内 ABI，张量/调用/状态。
- c/src/ir_core.c：纯 C 核心，不依赖 Python、文件系统、malloc 或模型名称。
- inference_ref/c_backend.py：ctypes 绑定、编译、报告与验证。
- c/tests/test_core.c：直接 C ABI 测试，可独立编译并使用 ASan/UBSan。

当前已验证 WSL Ubuntu x86_64 + GCC 15.2。Python 和 C 库必须在同一运行环境。
Windows Python 不能加载 Linux .so；Windows 请运行 WSL 入口。
未验证 Windows 原生 DLL、其他 CPU 架构、RV32 编译或板端性能。

## C 接口

ir_tensor：data、byte_length、dtype、layout、rank、shape[4]、storage_shape[4]。
这是原生 ABI，不是 fixture-v1 的磁盘格式。支持 1—4 维 row_major，
单张量最多 1,048,576 个存储元素；数据指针对 float/int32_t 正确对齐。
shape 是逻辑前缀切片，storage_shape 可以更大。输入 padding 必须为数值零。
输出 padding 不读取也不改写；输出稍后用作输入时，调用方须确保 padding 合法。

ir_call：op、a、b、bias、output、workspace、workspace_bytes。
LINEAR 中 a=W[N,K]、b=x[K]、bias 可选[N]，输出[N]。
ADD 中 a、b 和 output 同形状，无 bias；RELU 只有 a 和 output。
全部张量同 dtype，不广播，不做隐式精度转换。

| API | 行为 |
| --- | --- |
| ir_query | 检查支持情况、描述符、形状、容量、别名和 workspace；不执行数值运算 |
| ir_execute | 再次验证元数据、检查输入值、计算到工作区，全部成功后提交输出 |
| ir_execute_chain | 先检查全部节点元数据，再依序执行，返回 completed_steps |
| ir_status_name | 稳定错误名称 |
| ir_abi_version / *_struct_size | Python 加载时核对 ABI，拒绝不匹配的结构 |

调用方拥有所有缓冲区，保证实际内存与描述符一致、整个调用期间有效，
描述符本身及调用数组不能被输出/工作区覆盖。库不能验证任意 C 指针的真实性。
workspace 至少为 product(output.shape)*4 字节；调用不分配内存。
output 不得与当前节点任何输入或 workspace 重叠；
链中 workspace 不得与任意节点的输入/输出重叠，节点之间可以复用同一工作区。
不支持原地算子。

查询通过不表示数值输入合法，NaN/Inf、非零 input padding 和最终数值溢出在执行时拒绝。
单节点失败：output 原内容保持，workspace 内容未定义。
completed_steps 必须是独立、对齐的 uint32_t 存储，不能与调用数组、张量描述符、
声明的张量容量区间或工作区重叠。有效节点数下，计数器别名或声明地址区间无效时，
在首次写计数器前返回 INVALID_ARGUMENT，计数器原内容保留。
其余链元数据失败：不执行任何节点，completed_steps=0。
链执行失败：较早成功节点保留，当前/后续节点输出保持；不承诺整链事务回滚。
状态为 INVALID_ARGUMENT、INVALID_SHAPE、UNSUPPORTED、RESOURCE_LIMIT、
NONFINITE、NUMERIC_OVERFLOW；具体定义见头文件。

## 数值

INT32 乘积提升到 int64_t，累加采用两个 uint64_t limb 的带符号幅值表示。
在本工具上限内，中间幅值小于 2^83，最终才检查 INT32，不使用有符号溢出、
不使用 __int128、不回绕/饱和。超过 INT64 后再抵消的结果仍可正确输出。

FP32 要求 IEEE binary32/binary64 和 round-to-nearest；其他舍入模式明确拒绝。
乘积在 double 中精确表示，浮点展开求和保留消去项，最后舍入到 float。
最多 64 个展开分量，超出返回 RESOURCE_LIMIT，禁止静默丢失分量。
最终以 IEEE 舍入溢出边界判断；略高于 FLT_MAX 但舍入有限的值仍接受。
使用 -fno-fast-math、-ffp-contract=off 和标准 excess precision，不允许 reassociation。
本轮按已有容差验收，不承诺未来所有硬件/算子逐位一致。

## Python 桥接与验证

Tensor 从输入 ndarray 复制并按原 storage_shape 补零，以原生 float32/int32 建立 C 描述符；
不把 fixture 中的小端字节直接解释成跨平台指针。所有 C 调用期间保持 NumPy 所有者存活。
Call 绑定显式 Tensor，跨节点共享的是同一 C 张量，不从 Python 参考复制中间答案。
CBackend.run_chain 对四节点链只调用一次 ir_execute_chain。

四节点演示为 linear(bias) -> relu -> add -> linear，FP32/INT32 各一条；
逐节点对齐 Python，最终结果再对齐手算 [20,-25]。
调用链数值失败也记录 status、completed_steps 和比较结果，报告 passed=false，退出码为 1。
单算子 54 个样本分别对齐：保存 expected、Python 标量、NumPy。
C 核心接收输入和空白 output，从不接收 expected 的值。

## 执行

Linux/WSL，在本目录运行：

    IR_REQUIRE_C=1 python3 -m unittest discover -s tests -v
    python3 -m inference_ref verify-c --fixtures fixtures/synthetic-v1 --output build/a4_run_new

Windows PowerShell 可以调用：

    wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec env IR_REQUIRE_C=1 python3 -m unittest discover -s tests -v
    wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec python3 -m inference_ref verify-c --fixtures fixtures/synthetic-v1 --output build/a4_run_new

依赖：C11 GCC/Clang 风格编译器、Python/NumPy；verify-c 默认执行 sanitizer 编译与运行。
可用 --cc 指定编译器可执行文件，不是 shell 命令。
输出目录必须不存在，且不得位于输入样本树中。
包含 backend/ 的库、编译日志和 build.json，native_tests/ 的直接 C sanitizer 证据，
以及 report.json（编译命令/工具版本、源码/二进制/样本哈希、逐样本和调用链结果）。
source=pc_c_backend，不标为实板结果，也不从这些时间推导板端性能。

退出码：0 验收通过；1 数值/原生 C 测试失败；2 工具、参数、编译或输出冲突。
缺少编译器时 verify-c 必须失败。普通 unittest 环境无编译器会显式 skip C 测试；
验收必须设置 IR_REQUIRE_C=1，防止只跑 Python 后误报 C 已验证。
