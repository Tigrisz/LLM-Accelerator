# S1：阶段 1A 基线固化验证报告

2026-10-24；统一基线 phase1a-s1，工具 0.1.1；范围见 s1_plan.md。

## 完成内容

- 修复 compare_arrays 的零维失败首坐标：[]；无失败为 null。
- 保留相同 dtype/形状、整数精确、浮点容差及非有限值拒绝等现有行为。
- 工具补丁 0.1.0 -> 0.1.1，文档契约修订 v0.1.1；磁盘格式 version=1、C ABI=1 不变。
- phase1a_baseline.md 汇总版本、当前 API/支持集、设计边界、历史证据规则和复现命令。
- README 和分模块说明统一指向当前基线；历史 A1—A7 报告保留原始计数与指纹。
- 新验收证据独立存放；不重新生成或改写 fixtures/synthetic-v1，不改变 C 核心。

## 修复证据

原因为 argwhere 的零维失败结果 shape=(1,0)，虽然有一行坐标，但 size=0。
旧实现以 size 判断存在性，导致 first_mismatch=null；现按行数判断。

新增两项测试先运行，7 个子场景均复现 None != []；最小修复后通过。
覆盖 int32/float32 标量、相等、容差内、NaN/Infinity（含参考非有限）与 JSON 序列化。
不扩展 TensorSpec、样本或模型包的 rank 1—4 限制，不新增标量算子。

## 当前实际验证

| 验证项 | 结果 |
| --- | --- |
| Windows Python 3.12.14 / NumPy 2.3.5 参考专项 | 17/17，通过 |
| WSL Ubuntu x86_64 / Python 3.14.4 / NumPy 2.3.5 / GCC 15.2.0 完整套件 | 107/107，无跳过 |
| verify-trace 54 冻结样本 | 54/54，追踪开关逐字节一致 |
| stored/scalar/NumPy 对实际 C 比较 | 162 项，通过 |
| FP32/INT32 四节点链与生命周期场景 | 2 条链、8 场景，通过 |
| 采集溢出/异常探针 | 计算/释放正确，日志明确不完整 |
| 8 种记录缺失/篡改负面对照 | 全部被拒绝 |
| 原生 C 直接测试与 ASan/UBSan | 通过，stderr 为空 |
| 主追踪 | 2978 事件，complete=true，无丢失/采集错误，导出回读通过 |
| 修改前后冻结文件/C 源码与测试 | 109 个冻结文件、整个 c/ 目录指纹不变 |
| 新报告来源 | environment.tool=0.1.1，源码指纹与当前文件一致 |

正式证据：build/s1_unittest_final.log、build/s1_reference_windows.log、
build/s1_validation_final/report.json 及其 backend/native_tests/trace/observation_probes/。
修改前指纹 build/s1_preflight.json；最终版本/文件/证据收据 build/s1_baseline.json。
IR_REQUIRE_C=1 保证完整测试环境缺编译器时报错；不把跳过 C 测试视为通过。

复现：本目录 WSL/Linux，输出必须使用不存在的新名称：

    IR_REQUIRE_C=1 python3 -B -m unittest discover -s tests -v
    python3 -B -m inference_ref verify-trace --fixtures fixtures/synthetic-v1 --output build/s1_run_new

## 独立审查

已请求一次新上下文只读审查；代理在实际审查前因使用额度限制退出，未提供审查结论。
因此本轮没有“独立审查通过”证据，也不宣称独立审查发现零问题。
依用户明确要求继续，改为完成作者自查：

- 重读比较器与新增测试，核对零维、非有限、容差和非零维行为；额外 10 个
  int32/float32、rank 0—4 首坐标内存探针通过。
- 对照实际导出/读取定义检查工具、文档、磁盘格式、C ABI 和可选 profile 的版本表。
- 核对新旧报告归属、旧冻结 generator=0.1.0、当前 environment.tool=0.1.1，
  及当前源码、C 二进制、原生测试二进制与报告指纹的一致性。
- 完整检查本轮修改清单：仅指定目录内 13 个已有文件修改、3 个文档新增，无删除；
  C 核心与 109 个冻结文件不变，未实施 S2—S6。

自查不提供独立视角。真实模型、RV32/FPGA、板端性能、未实现的量化/生成/驱动，以及
进程 RSS/多会话全局内存上限不在 S1 验收范围，不以本次测试代替这些后续验收。

最终 build/s1_baseline.json 记录 review.independent.status=unavailable 和自查状态，
包含版本、56 个项目文件、109 个冻结输入及验收证据 SHA256；
build/s1_baseline.sha256 单独保存该清单自身指纹。清单回读逐文件核对后交付。

## 边界

S1 不包含 S2—S6、真实模型、W4A8 或其他量化配置、板端平台/驱动与 RV32/FPGA 验证。
现有 C 为 PC 正确性路径；Windows 专项不等于 Windows 原生 C/DLL 验收。
旧报告的工具 0.1.0 与旧源码哈希保留，不能用它们说明本次补丁已经验收。
基线指纹是本地内容快照，不是认证签名或远端发布；未提交、未推送。
