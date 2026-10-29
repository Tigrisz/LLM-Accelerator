# 推理框架：阶段 1A（A1—A7）

T8[当前版本统一总验收](docs/t8_validation_report.md)：单入口 `tools/reproduce_total.py` 在同一干净副本先验PC，再运行54个原样本与两条原四节点链，重放单/双发射实际证据及正向、异常恢复、容量负控；最终状态见报告。保留容量阻断/失败/未知，实板独立标记未知。

T7[原FP32/INT32四节点链RV32迁移](docs/t7_validation_report.md)：原形状/常量/输入、双发射配置对照、重复/同步未知及第三节点故障恢复；实际状态见报告，保留PC/仿真/实板边界。

T6[冻结FP32样本RV32迁移](docs/t6_validation_report.md)：沿用原数值语义与容差，核对FP64软浮点库、舍入/次正规/非有限/溢出，单、双发射对照27例；实际验收状态见报告。实板、完整最坏栈、真实模型保持未知。

T5[冻结INT32样本RV32迁移](docs/t5_validation_report.md)：同步S6能力口径，保持原shape/storage/payload，一例一固件对齐Python/PC C与单/双发射，重复/异常/恢复分列。T5当时不含FP32目标，后续T6单列；历史证据不回写。

当前T4收尾见[收尾记录](docs/t4_closeout_report.md)和[复现/字段说明](docs/rv32_bringup.md)：默认portable-metadata选择本地兼容RTL，要求同一ELF单/双发射都通过；报告v2新增rtl_profiles/v1分别汇总实际参数/构建命令/结果/负控。runtime仍0.6.0/nativeABI2，实板、形式等价、综合时序及完整最坏栈未知。

T4D[历史定位记录](docs/t4_dual_debug_report.md)：原始RTL/封存同一ELF在Icarus通过，Verilator5.032的FIFO元数据更新排序出现差异；本地组合wire兼容改写使最小例和原完整链通过。保留`--rtl-mode upstream`原始对照，归档/上游/旧基线不变。T4D当时延期的参数汇总和历史措辞两项在本次T4收尾中关闭。

初次T4[历史验证记录](docs/t4_validation_report.md)：原始RTL在Verilator5.032单发射通过、双发射失败，这是当时结果；后续T4D已定位并以兼容方案验证，不代表当前兼容方案失败，也不证明硬件缺陷或部署就绪。

T3[历史纯C元数据与栈优化](docs/t3_metadata.md)：运行时0.6.0/nativeABI2，context移除固定数组，按实际T提供T字节状态和4T字节临时检查区；旧原生调用方须迁移重编译。磁盘格式/ir_coreABI/平台与后端函数表保持。T3当时只测PC、目标布局和峰值未知，见[历史验证记录](docs/t3_validation_report.md)；T4后续增加了受测RV32布局和有限路径栈观测，完整最坏栈仍未知。

T2历史[目标平台约束清单](docs/target_platform_constraints.md)及[54项机器可读记录](docs/target_platform_constraints.json)：
覆盖工具链/ABI/端序/浮点/内存/栈/读取/计时/同步，13项未知显式保留，目标预算为null，未新增板端执行能力。
离线核对：`python3 -B tools/check_target_platform.py --output build/t2_audit_new.json`；边界见[T2验证记录](docs/t2_validation_report.md)。

T1新增[干净副本统一构建/验收入口](docs/reproducible_build.md)，工具格式v1，当前运行时0.6.0，T1历史受测版本0.5.0：

```text
python3 -B tools/reproduce.py --output build/t1_run --iterations 200
```

该入口不携带历史build，重新构建C、运行固定174项及独立工具测试、54样本/双链/资源压力和无历史依赖S6审计。
完整环境要求、Windows经WSL调用及结果位置见上述说明；本轮记录见[验证说明](docs/t1_validation_report.md)。

当前运行时 **0.6.0 / 资源账本API1 / 纯C native ABI2**；T3引入ABI2，T4仿真报告为v2、配置汇总rtl_profiles为v1。S6新增[候选模型接入清单](docs/model_intake.md)、
[能力矩阵](docs/capability_matrix.md)与[差距分析](docs/model_gap_analysis.md)，资料/模板v1，不扩展执行支持。
平台/后端函数表API仍为1，纯C native运行时ABI2，C PC服务结构ABI2；原生调用方须重编译迁移。
[纯 C 静态运行时](docs/static_runtime.md)，平台接口见
[PC 平台服务](docs/platform.md)。S2 整链后端接口见
[静态整链后端](docs/backends.md)。S1 固化基线作为历史快照保留，版本入口见
[阶段 1A 基线](docs/phase1a_baseline.md)，S1 历史结果见 [S1 验证说明](docs/s1_validation_report.md)。
S1 修复零维比较首坐标；现有磁盘格式 version=1、ir_core数值 ABI=1 保持兼容，T3运行时native ABI另为2。
S1 历史验收：107/107 全量测试无跳过、54/54 样本与 162 比较通过；
证据 build/s1_validation_final/report.json、build/s1_unittest_final.log。

已落实模型无关的接口契约、测试样本格式和 Python 参考计算路径。
新增 A4：PC 侧 C11 算子后端与最小顺序调用链；不是完整模型推理引擎或 FPGA 驱动。
新增 A5：模型无关数据包加载、静态 arena 内存规划和 PC C 会话执行。
新增 A6：逻辑事件模拟设备、任务生命周期与缓冲区 lease，执行仍走 C 后端。
新增 A7：模型/内存/主机阶段/C 节点/设备任务关联追踪，JSON、时间线和统计导出。
没有绑定当前 Qwen 模型、W4A8、128 分组或 16/32 路硬件配置。
S2 新增可替换整链后端、逐节点能力查询、显式选择/回退和实际后端追踪；默认仍为 PC C。
S3 新增平台读取、受管对齐内存、主机时间源与 host-coherent 同步；32 位仅验证范围，不代表 RV32 执行。
S4 新增 PC 离线导出、无指针二进制执行描述、调用方 arena 绑定、纯 C 平台/后端回调及独立运行程序。
S5 新增共享资源预算/分类峰值、C元数据和可选profile计账、追踪缓存关闭、任务staging/记录/历史上限，以及压力验收CLI。
S5最终验收：174/174无跳过（S5新增13项），24/24压力探针、2400个重复任务、40个故障位置、
各后端50次恢复拒绝及关闭重试，最终受管资源归零；嵌套54样本/双链/ASan/UBSan通过。
计量是受管载荷/记录数，非RSS；证据build/s5_validation_final/report.json、s5_unittest_final.log、s5_baseline.json。
独立 C 程序运行不依赖 Python；离线导出和参考比较使用 Python。原 C 数值核心保持不变。
S4 最终验收：161/161 无跳过（S4新增9项），54/54样本、162参考比较、独立/适配逐字节对照、
双类型四节点链正常/零输入、5项C追踪负控和实际ASan/UBSan通过；资源归零。
证据 build/s4_validation_final/report.json、build/s4_unittest_final.log、build/s4_baseline.json。
S3 最终验收：152/152 无跳过（新增25项），54/54样本、162比较、5故障/范围探针及嵌套S2/A7/C sanitizer通过。
证据 build/s3_validation_final/report.json、build/s3_unittest_final.log、build/s3_baseline.json。
S2 最终验收：127/127 无跳过（新增 20 项），54/54 样本逐字节一致、162 比较、
54 次显式回退与原 A7 全路径通过；证据 build/s2_validation_final/report.json、build/s2_unittest_final.log。

## 阅读入口

- docs/contracts.md：模块边界、张量、模型/会话、后端、平台和数值契约。
- docs/fixture_format.md：fixture-v1 的准确字段、二进制布局、校验和失败规则。
- docs/phase1a_baseline.md：当前统一版本、实现边界、证据和复现命令。
- docs/phase1a_plan.md：A1—A3 历史范围和验收项。
- docs/validation_report.md：A1—A3 历史验证；延期零维问题已由 S1 修复。
- docs/progress.md：执行过程、选择和审查记录。
- docs/c_backend.md：A4 C ABI、数值、编译和调用链说明。
- docs/a4_validation_report.md：A4 编译与数值验证结果。
- docs/model_package.md：A5 包格式、加载/内存/会话接口和运行方法。
- docs/a5_validation_report.md：A5 端到端验证结果。
- docs/sim_device.md：A6 模拟设备、状态、超时/取消/恢复与接口。
- docs/a6_validation_report.md：A6 生命周期和 C 集成验收。
- docs/tracing.md：A7 开启方式、覆盖、时钟、预算及导出格式。
- docs/backends.md：S2 后端 API、策略、未知执行恢复与验收命令。
- docs/s2_validation_report.md：S2 验证结果及限制。
- docs/platform.md：S3 平台接口、资源生命周期、地址/同步/时钟边界及验收命令。
- docs/s3_validation_report.md：S3 验证结果与审查记录。
- docs/static_runtime.md：S4 二进制格式、C 平台/后端接口、生命周期与复现命令。
- docs/s4_validation_report.md：S4 验收结果与限制。
- docs/resources.md：S5 资源计量口径、预算、生命周期与压力验收。
- docs/s5_validation_report.md：S5 验证结果和审查限制。
- docs/model_intake.md：S6 接入检查清单、状态判定与资料采集流程。
- templates/*_v1.json：候选/算子/张量/量化需求空白模板；未知保留null/pending，不是可执行模型包。
- docs/capability_matrix.md：当前支持集与源码/证据依据。
- docs/model_gap_analysis.md：候选触发的能力缺口、条件转换与验收条件。
- docs/model_memory_requirements.md：分profile内存采集、预算公式及未计开销。
- docs/s6_validation_report.md：S6 资料核验与限制。
- docs/reproducible_build.md：T1 单入口、源快照、空build验收与工具依赖。
- docs/t1_validation_report.md：T1 干净副本验证说明和证据位置。
- docs/a7_validation_report.md：A7 开关对照和追踪验收证据。

## 内容

inference_ref/contracts.py 提供基础张量和算子合法性检查。
reference.py 使用 Python 标量、math.fsum 和任意精度整数计算。
oracle.py 独立使用 NumPy 矩阵/数组运算；两条路径不互相调用计算实现。
fixtures.py 提供带来源、形状和 SHA-256 的样本写入/读取。
suite.py 和命令行提供确定性样本生成及三方核验。
fixtures/synthetic-v1 保存本轮冻结的合成/手算样本。

本轮执行子集：float32/int32，linear（可选 bias）、add、relu。
其他格式、布局和算子明确拒绝。静态包/会话已实现，完整模型生成接口仍为契约说明。
C 实现在 c/，Python 绑定/构建与比对在 inference_ref/c_backend.py。
model_package.py、memory.py、runtime.py 实现 A5；package_validation.py 提供真实模型包验收路径。
sim_device.py、device_validation.py 提供 A6 协议模拟与端到端验证。

## 运行

Python >=3.10、NumPy >=1.24。已有可用 NumPy 时无需安装其他依赖。
在本目录运行，以下命令中的 python 应指向装有 NumPy 的 Python：

    python -m unittest discover -s tests -v
    python -m inference_ref verify --fixtures fixtures/synthetic-v1 --report build/reference_report_new.json
    python -m inference_ref generate --output build/synthetic_new
    python -m inference_ref verify --fixtures build/synthetic_new --report build/synthetic_new_report.json

生成目录和报告必须不存在，重复运行换新名称。核验不会改写 frozen fixtures。
退出码 0 通过；1 样本验证失败；2 参数/格式/I/O/输出覆盖错误。
报告记录工具/Python/NumPy/平台、输入哈希和核心源码哈希。

C 验收请使用装有 C 编译器的同一 Python 运行环境，目前已验证 WSL Ubuntu：

    IR_REQUIRE_C=1 python3 -m unittest discover -s tests -v
    python3 -m inference_ref verify-c --fixtures fixtures/synthetic-v1 --output build/a4_run_new

Windows PowerShell 的 WSL 调用命令和输出内容见 docs/c_backend.md。

以下 A4—A7 为各阶段历史结果；当前补丁验收以 S1 新证据为准。

2026-10-24 A4 最终验收：46/46 测试无跳过，54/54 原样本、162 项 C 比较、
两条四节点 C 调用链通过；直接 C ASan/UBSan 通过。
记录在 build/a4_validation_final/report.json 和 build/a4_unittest_final.log。

A5 的 WSL/Linux 验收和检查命令：

    python3 -m inference_ref verify-packages --fixtures fixtures/synthetic-v1 --output build/a5_run_new
    python3 -m inference_ref inspect-model --package build/a5_run_new/chains/int32

A6 验收：

    python3 -m inference_ref verify-device --fixtures fixtures/synthetic-v1 --output build/a6_run_new

A7 验收：

    python3 -m inference_ref verify-trace --fixtures fixtures/synthetic-v1 --output build/a7_run_new

S2 验收入口：

    python3 -B -m inference_ref verify-backends --fixtures fixtures/synthetic-v1 --output build/s2_run_new

S3 当前验收：

    python3 -B -m inference_ref verify-platform --fixtures fixtures/synthetic-v1 --output build/s3_run_new

A7 最终验收：105/105 完整测试无跳过，54/54 样本追踪开关逐字节一致、162 比较、
双类型链、8 生命周期场景、2 观察故障探针、8 语义负面对照和原生 C ASan/UBSan 通过。
主追踪 2978 事件，无丢失/采集错误；证据 build/a7_validation_final/report.json、build/a7_unittest_final.log。

A6 最终验收：90/90 完整测试无跳过，54/54 样本、162 比较、两条四节点包、8 项生命周期场景
和原生 C ASan/UBSan 通过；资源归零。证据 build/a6_validation_final/report.json、build/a6_unittest_final.log。

A5 最终验收：71/71 完整测试无跳过，54/54 模型包、162 项比较、两条四节点包与
原生 C ASan/UBSan 通过。证据 build/a5_validation_final/report.json、build/a5_unittest_final.log。

## 验收边界

手算样本和两条独立参考核验基础数值语义；固定种子覆盖随机非方阵和 padding。
FP32 工具使用 FP64 累加后舍入，不承诺与任意硬件 FP32 累加逐位一致。
基础样本容差不是完整模型精度门槛。
随机样本使用 PCG64，版本记录在来源中；跨 NumPy 版本不承诺重新生成逐字节相同，
冻结样本的字节和校验信息才是对应版本的依据。

A4 最小 C 算子调用链、A5 静态模型包/运行时内存规划、A6 模拟设备任务生命周期、
A7 当前静态运行时完整追踪已实现。A6 仍为单所有者线程协作式模拟，不代表真实 DMA/异步抢占。
现有 A5 是 PC Python 加载器与 C 数值路径，不代表板端 C 加载器或完整生成会话。
模型确定后进入 1B；当前算子与数值选择不固定未来模型/量化方案。
S2—S5 已实现，S6接入准备资料已整理；需候选真实清单、参考输出和目标资源后才能判断实际接入。
