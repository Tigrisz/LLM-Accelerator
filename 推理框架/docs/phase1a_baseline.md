# 阶段 1A 当前基线：phase1a-s1

历史快照说明：下文对应S1/工具0.1.1；S2—S5已继续开发，当前工具0.6.0，T3 native ABI2见t3_metadata.md，资源见resources.md。
S6新增模型接入准备资料v1，见model_intake.md；本轮不修改运行时或ABI。
build/s1_baseline.json 保持封存，不能用它要求 S2 源码与旧指纹相同；冻结输入/C 核心仍沿用。

本页是 S1 后的统一入口；工具版本 **0.1.1**，文档契约修订 **v0.1.1**。
A1—A7 在下述 PC 静态支持范围内完成。S1 修复比较器标量坐标并收口说明，
不新增模型、量化、算子、板端驱动或设备配置。历史过程见 progress.md。

## 版本与兼容性

工具、格式和原生 ABI 分开编号，不能用工具补丁号代替文件 version。

| 对象 | 当前版本/判据 | 权威定义与说明 |
| --- | --- | --- |
| Python 工具/Python API | 0.1.1 | inference_ref/__init__.py 的 __version__；API 随工具发布，无独立协议协商 |
| 文档接口契约 | v0.1.1 | contracts.md；为说明修订号，不写入磁盘包/任务 |
| 单样本 | inference-fixture / version=1 | fixtures.py、fixture_format.md |
| 样本集合 | inference-fixture-suite / version=1 | suite.py；generator 记录创建工具版本，不是格式版本 |
| 静态模型包 | inference-model-package / version=1 | model_package.py、model_package.md |
| 原生 C ABI | IR_ABI_VERSION=1 | c/include/ir_core.h；加载时检查 ABI 与 tensor/call 尺寸 |
| C profile | ABI 1 可选扩展，无独立版本号 | 查询导出符号和 profile 尺寸；缺能力仍运行普通 C，trace 不完整 |
| 原始追踪 | inference-runtime-trace / version=1 | tracing.py、tracing.md |
| 追踪导出清单 | inference-trace-export / version=1 | manifest.json 的文件长度与 SHA256 |
| 追踪摘要 | inference-trace-summary / version=1 | 由原始追踪派生，并在回读时核对 |
| 时间线 | Trace Event JSON | 不另设本项目 version；host 微秒 ts/dur，CPU/逻辑时间仅在 args |
| 验收报告 | 各自 format / version=1 | 见下表；environment.tool 记录此次工具版本，历史报告不改写 |

| 验收路径 | report.format |
| --- | --- |
| verify | inference-reference-report |
| verify-c | inference-c-report |
| verify-packages | inference-package-report |
| verify-device | inference-device-report |
| verify-trace | inference-trace-validation-report |

S1 是兼容补丁：不改变比较门槛、算术、报告字段、磁盘布局或 C 结构。
first_mismatch 的零维失败值由错误的 null 更正为 []；无失败仍为 null。
未来修改格式或 ABI 时必须明确制定新版本与兼容策略，不能静默解释未知字段/版本。
各格式的拒绝状态以其读取器/文档为准，不保证所有格式使用同一错误码。

fixtures/synthetic-v1 是冻结输入：54 样本、27 float32 + 27 int32、109 文件。
其中 generator=inference_ref/0.1.0 是真实创建来源，不随本次工具升级改写。
新生成集合会记录 0.1.1，因此不承诺其 suite.json 与旧冻结集合逐字节相同。

## 当前可执行接口

| 模块 | 已实现接口/行为 | 边界 |
| --- | --- | --- |
| 基础参考 | TensorSpec；reference.execute / oracle.execute | float32/int32，linear 可选 bias、add、relu，张量 1—4 维行优先 |
| 比较器 | compare_arrays(expected,actual,atol=1e-6,rtol=1e-5) | 直接调用还接受零维 ndarray；不广播/转换 dtype；非空且同形状/类型 |
| 样本 | read_fixture / write_fixture；generate / verify | fixture-v1；padding/长度/来源/哈希检查 |
| C 核心 | ir_query、ir_execute、ir_execute_chain、可选 ir_execute_chain_profiled | 原生进程内调用；不是磁盘格式或设备协议 |
| 包/内存/会话 | read_package / write_package；inspect_model、load_model、plan_memory、create_session；Session.run/close | Python 检查与规划 + C 计算；静态图，无动态形状或持久生成状态 |
| 模拟设备 | SimDevice.query_support/create_session/submit/poll/wait/cancel/recover/result/release/advance/drain/quiesce/close | 接收当前静态包，单所有者线程、逻辑 tick、会话 lease，无真实设备 |
| 追踪 | TraceRecorder；load_model/create_session/SimDevice 的 trace 参数；export/read_export/validate_trace | 有界元数据，host/CPU/逻辑时钟分离；丢失/采集错误标为不完整 |

准确签名、上限、错误与所有权以各模块文档及实现为准。以下仍是设计或后续任务：
完整模型适配、prefill/step/reset_session、tokenizer、KV Cache、量化执行、
可替换通用后端、板端 C 包加载/运行时、平台读取/内存/同步及真实 DMA/MMIO/中断。
SimDevice 的存在不等于已有硬件驱动；静态 Session.run 不等于 token 生成接口。

比较器的 first_mismatch：成功为 null；失败为按行优先找到的首个坐标列表。
零维坐标为 []，向量如 [0]，矩阵如 [1,2]。NaN/Infinity 不通过，缺失误差指标为 null。
这不改变 TensorSpec/fixture/model-package 的 rank 1—4 限制，不增加标量算子支持。

## 可复现验收入口

推荐在已装 NumPy 与 C 编译器的 WSL/Linux、项目目录下依次运行：

    IR_REQUIRE_C=1 python3 -B -m unittest discover -s tests -v
    python3 -B -m inference_ref verify-trace --fixtures fixtures/synthetic-v1 --output build/s1_run_new

输出目录必须不存在；再次执行换一个新名称，不能覆盖旧报告或冻结样本。
Windows PowerShell 使用同一 WSL 环境：

    wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec env IR_REQUIRE_C=1 python3 -B -m unittest discover -s tests -v
    wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec python3 -B -m inference_ref verify-trace --fixtures fixtures/synthetic-v1 --output build/s1_run_new

第一条要求全部测试通过且无跳过；IR_REQUIRE_C=1 令缺少 C 编译器成为失败，
不能以只有 Python 的测试通过冒充完整验收。第二条要求退出 0 且 report.passed=true，
包含 54 样本/162 比较、开关逐字节一致、双类型链、8 生命周期场景、2 观察故障探针、
8 语义负面对照、导出回读、原生 C ASan/UBSan 及冻结输入不变。
负面对照预期 trace validation=false；这与整体报告 passed=true 不矛盾。
CLI 退出 1 表示验收不通过；2 表示参数/工具/I/O/输出冲突，不得解释为通过。

S1 的新正式证据：build/s1_validation_final/report.json、build/s1_unittest_final.log；
Windows Python 标量/参考专项另见 build/s1_reference_windows.log。
build/s1_baseline.json 固化本轮版本、输入/源码/文档/测试指纹和证据文件哈希。
build/s1_baseline.sha256 为清单自身的 SHA256；review 字段如实记录独立审查未能执行、作者自查已完成。
它是内容快照，不是认证签名，也不是 Git 提交或远端发布。
S1 结果与范围见 s1_validation_report.md；基线复验需要同时比较文件指纹与实际运行结果。
只核对哈希能够发现已列文件内容变化，不能代替重新运行验收，也不证明未来新增文件已被检查。

## 证据解释与限制

旧 validation_report、a4/a5/a6/a7_validation_report 及对应 build 目录是阶段历史证据。
不修改其原工具版本、源码哈希或测试计数；当前判断使用 S1 新证据，不能直接把旧指纹当成当前源码。
工具补丁版本与固定输入保持独立：冻结文件变化需要单独批准的新样本基线。

PC 测试不代表 RV32/FPGA 等价、性能或完整模型质量；FP32 参考规则不自动适用于任意硬件。
arena 预算不是进程 RSS/多会话全局上限，host 跨度不可直接相加为硬件耗时。
量化/生成/硬件均需独立需求与验收，不从当前小型算子支持集外推。
本地文件快照不承诺已经暂存、提交、推送或集成主仓库。
