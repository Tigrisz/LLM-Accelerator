# A4 PC 最小 C 算子调用链实施计划

日期：2026-10-24。依据：已确认的阶段 1A 方案及本轮用户授权。

目标：可移植 C11 基础后端执行 float32/int32 linear（含可选 bias）、add、relu；
通过顺序调用链组合这些算子；用原有 54 个冻结样本对齐保存答案与 Python 双参考。

## 范围和文件

- c/include/ir_core.h：张量/算子/状态和同步调用链 ABI。
- c/src/ir_core.c：元数据、缓冲区检查、数值计算与顺序调度；无 malloc/文件/Python 依赖。
- c/tests/test_core.c：直接调用 C ABI 的边界/错误/组合测试。
- inference_ref/c_backend.py：编译、加载、Python 张量绑定及 54 样本/链路核验。
- tests/test_c_backend.py：编译产物、数值、调用链、错误原子性、CLI 和输入不变回归。
- 文档：c_backend.md、a4_validation_report.md；更新 README 和当前能力说明。

## 契约选择

原 fixture-v1 不变；Python 读取/校验 JSON，C 只接收张量与算子，不接收参考答案。
逻辑/存储形状传入 C，支持真实 padding，输出 padding 不改写。
调用方提供输出和工作区；单算子失败不提交输出。链中较早成功节点不回滚，
失败节点与后续节点不提交；completed_steps 精确记录成功数。
查询/执行均验证元数据，执行额外检查输入数值；不支持的 dtype/layout/op 明确拒绝。

INT32：使用两个 uint64 limb 的带符号幅值累加，不依赖 __int128；
在工具张量上限内可精确容纳全部乘积，仅最终输出做 INT32 范围检查。
FP32：输入提升为 double，以浮点展开求和保留消去项，再舍入到 float；
要求 IEEE binary32/binary64、round-to-nearest；禁用 fast-math 和乘加融合。
不宣称与所有参考实现逐位一致，仍按原 atol=1e-6/rtol=1e-5 验收。

## 顺序

1. 先写 Python/C 契约测试，观察缺失功能失败。
2. 实现 C ABI 和核心，Python 仅负责绑定及构建；通过数值/边界测试。
3. 加入 verify-c 入口及 54 样本三项比较和四节点顺序链。
4. 完整旧/新回归、独立 C 测试及 ASan/UBSan、只读独立审查、最终复验。

## 重点检查

整数累加超过 INT64 后抵消；浮点消去、舍入边界、非有限输入；
逻辑尺寸/存储跨度、短缓冲、别名与错对齐；失败后输出保持；
C 真实执行且未接收 expected；冻结样本不变；无编译器不能冒报 C 验收通过。

## 执行记录

- 原地在用户指定目录实施，不改上层 Git、不提交推送。
- 基线：原 34 项测试通过；沙箱内 WSL 访问受限，获准的主机执行可用。
- 工具：WSL Ubuntu x86_64，GCC 15.2.0，Python 3.14.4，NumPy 2.3.5。
- Ruling：本轮以 WSL PC 为已验证 C 环境；不安装额外 Windows 编译器。
  代价：Windows 原生编译/DLL ABI 未验证，不能据此宣称支持。
- 审查后新增两项回归，分别复现计数器别名和链失败报告中断；修复后均通过。
- 最终：46/46 测试无跳过，54/54 样本、162 项 C 比较、两条四节点链全部通过。
  直接 C ASan/UBSan 返回 0；独立只读复核确认原问题闭合，无新增阻断项。
  证据见 a4_validation_report.md 和 build/a4_validation_final/。
