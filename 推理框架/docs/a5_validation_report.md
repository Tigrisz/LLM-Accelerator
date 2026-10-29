# A5 验证报告

日期：2026-10-24。实现范围与接口见 model_package.md；实施计划见 a5_plan.md。

最终状态：A5 完成。修复审查中的路径错误类型问题后，完整 71/71 项测试无跳过，
54/54 个模型包、162 项比较、两条四节点包及原生 C sanitizer 均通过。

## 已完成

- 数据包严格读写、常量校验、静态图检查、不可变模型记录。
- 生命周期与 first-fit 激活复用、padding 独立槽、共享 scratch、对齐及真实 backing 预算。
- PC 模型加载、会话创建/执行/关闭；直接 arena -> A4 C ABI，重复运行与失败重试。
- inspect-model、verify-packages；54 个原样本的模型包路径与双类型四节点包验收。

## 测试先行记录

- 原 A1—A4 的 46 项基线在 WSL 实际通过。
- 新包/规划 14 项测试先因缺失功能失败，实现后通过。
- 运行时 8 项测试先因缺失 runtime 失败；CLI 专项另复现缺失命令失败。
- 非普通文件读入拒绝新增回归先失败，再加入读取前检查后通过。
- 补充 24 个固定种子分支图，每图 8 节点、2 次运行、2 个输出，分别对齐 scalar/NumPy；
  混合 padded/compact、提前输出保留与激活复用，专项测试通过。
- A5 现有 24 项专项测试在 WSL 通过；最终完整套件、审查及正式报告待下方记录。

## 审查前完整结果

- A1—A5 完整 70/70 项测试通过，无跳过，37.420 秒。
- 54/54 个包通过，对齐 expected / scalar / NumPy 共 162 项比较通过。
- FP32/INT32 四节点包及重复运行通过，C 均 OK、completed_steps=4。
- 两个合成链：激活 arena 不复用 320 字节、复用后 128 字节；
  总 backing（含 3 个 arena 的对齐额外空间）不复用 829 字节、复用后 637 字节，节省 192 字节。
- 每个样本包实际 backing 字节数均等于内存计划；所有 109 个原 fixture 文件哈希保持一致。
- A4 原生 C 测试、ASan/UBSan 通过；C 源码和头文件哈希与 A4 最终报告相同。
- 证据：build/a5_validation_pre_review/report.json、build/a5_unittest_pre_review.log。

这些数字来自小型合成链，不表示实际模型需求、算子吞吐或 FPGA 性能。
最终独立审查及复验结果在下方记录。

## 独立审查与最终复验

独立只读审查：Critical 0、Important 0、Minor 1。
Minor 为包含 NUL 的非法根路径泄漏 ValueError；新增回归先实际复现失败，
将根路径类型/解析错误统一为 INVALID_ARGUMENT，文件系统错误统一为 IO_ERROR 后通过。
None 根路径和写包的非法根路径也纳入回归。没有把问题留给后续。

审查者独立做过 1573 次清单字段类型替换，除一次等价原值外均按 ContractError 拒绝；
真实 C 后段溢出返回 completed_steps=3，随后正常输入重试完成 4 节点；
close 后激活/scratch backing 的 weakref 失效。此为独立补充探针，未替代完整回归。

修复后正式验收：

| 项目 | 结果 |
| --- | --- |
| A1—A5 完整 unittest | 71/71，通过，无跳过；35.541 秒 |
| 模型包路径 | 54/54 个原样本，经写包、读取、预算规划和真实 C 会话执行通过 |
| 三项比较 | stored expected / Python scalar / NumPy 共 162 项全部通过 |
| 双类型合成包 | INT32、FP32，均 OK、4 节点完成；首次和重复运行结果正确 |
| 内存复用 | 两条合成链激活 320 -> 128 字节；总 backing 829 -> 637 字节，含对齐额外空间 |
| 分支/保留输出/padding | 固定种子 24 个 8 节点图、每图两次运行和两个输出，标量/NumPy 对齐通过 |
| 预算 | 计划值等于实际 backing；精确预算可用，少 1 字节先拒绝再申请 |
| 冻结输入 | 原 109 个文件前后 SHA256 相同，suite 哈希与 A4 最终报告相同 |
| 兼容性 | A4 C 源码和头文件哈希未变；旧测试全部通过 |
| 原生 C sanitizer | ASan/UBSan，C_CORE_TESTS_PASS，退出 0，stderr 为空 |
| 来源 | 最终报告的 A5 源码哈希均与当前文件匹配，C 编译/二进制哈希有记录 |

数值规则沿用 A1—A4：INT32 精确比较，FP32 atol=1e-6、rtol=1e-5。
正式执行环境：WSL Ubuntu x86_64、GCC 15.2.0、Python 3.14.4、NumPy 2.3.5。
另在 Windows Python 3.12.14/NumPy 2.3.5 实际 inspect 已生成模型包成功，
未据此声明 Windows 原生 DLL 或 C 会话执行通过。

## 最终证据

- build/a5_validation_final/report.json：逐样本比较、计划/实际 backing、调用链、文件/源码/工具环境。
- build/a5_validation_final/packages/：54 个实际写入、再加载的包，不含 expected 字段。
- build/a5_validation_final/chains/：两个独立四节点合成包。
- build/a5_validation_final/backend/：编译日志、build.json 和实际 C 动态库。
- build/a5_validation_final/native_tests/：直接 C 可执行文件、ASan/UBSan 命令及结果/日志。
- build/a5_unittest_final.log：71 项完整测试输出。

这些记录不是完整模型/板端验收。重新运行使用 model_package.md 的命令和不存在的新输出目录。
A6 模拟设备生命周期、A7 完整运行时追踪仍未实现，下一阶段需独立开展。

## 范围边界

PC Python 加载/规划 + C 数值执行；不是 RV32 板端 C 文件系统/JSON 解析器。
尚无真实模型/tokenizer/KV、动态形状、量化、FPGA/DDR/驱动和性能验收。
预算针对共享模型 + 单会话的 NumPy arena backing，额外包字节和 Python 对象不计入。
原生 ASan/UBSan 检查对象是直接 C ABI 核心测试，不是 Python 进程整体 sanitizer。
未修改冻结样本，不提交、不推送、不改其他项目。
