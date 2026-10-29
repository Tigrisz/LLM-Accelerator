# 阶段 1A（A1—A3）验证报告

历史报告：仅对应 A1—A3 当时的实现与指纹。A4—A7 和 S1 的当前范围/证据见
phase1a_baseline.md；本页测试计数与旧源码版本不作为 S1 当前结论。

开始：2026-10-23；最终复验：2026-10-24（Asia/Shanghai）。
本报告仅对应本目录新增内容。

## 已交付

- A1：模块/张量/数值/模型会话/后端/平台契约；基础张量和算子检查可执行。
  模型会话及硬件任务接口是后续设计，不冒称驱动已经实现。
- A2：fixture-v1 规范和读写校验。逻辑/存储形状、来源、端序、长度、
  完整 payload/张量/索引哈希以及 padding 均有检查。
- A3：标量和独立 NumPy 参考、严格比较器、生成/核验命令行、
  冻结的 54 个样本（14 个基础/手算/补齐样本、20 个种子各两种精度）。

## 已执行证据（审查前）

环境：Windows，Python 3.12.14，NumPy 2.3.5。

    python -m unittest discover -s tests -v

结果：33 个测试，全部通过。含测试内多组子用例，不将子用例额外计为测试数。
固定种子随机线性运算、手算结果、消去、最终溢出、NaN/Inf、dtype/shape 错误、
padding、篡改、截断、重复字段、路径、禁止覆盖、CLI 返回码均有覆盖。
补充发现超大整数容差及非对象 JSON 会抛出未归类异常，先复现后修复；
完整 33 项套件通过。

    python -m inference_ref generate --output fixtures/synthetic-v1
    python -m inference_ref verify --fixtures fixtures/synthetic-v1 --report build/reference_report_pre_review.json

结果：54/54 个样本通过，每个样本完成三项比较。
命令行退出码为 0；完整数值、环境、输入和核心源码哈希在该 JSON。
测试内还验证：
- 相同环境下两次生成的全部文件逐字节一致。
- 故意破坏保存答案并修复全部校验值，数学核验仍失败。
- 样本失败 CLI 返回 1，输出覆盖或非法调用返回 2。
- 全部报告可以严格 JSON 序列化，不输出 NaN/Infinity。

## 边界

这里只验证基础算子数值和工具契约，不验证模型质量、C/RTL 等价、设备性能、
DDR、KV Cache、tokenizer 或实板。没有运行原 AI 加速器的回归，
也没有修改原 CPU/AI 加速器文件。
未提交、未推送；未生成完整模型，也未下载 checkpoint。

## 独立审查与修复后最终结果

独立只读审查阅读文档/源码/测试，并重新读取核验 54/54 样本。
发现 0 Critical、1 Important、1 Minor，未修改文件或 Git 状态。

Important 已修复：FP64 中间结果略超 FP32 最大值时，可能仍舍入到有限 FP32。
旧实现过早比较绝对值；现改为先进行受控转换，再检查最终值是否有限。
新增 test_fp32_boundary_is_decided_after_rounding，先复现失败再修复，
同时覆盖正/负边界的有限舍入和真正溢出。

最终执行：

    python -m unittest discover -s tests -v
    python -m inference_ref verify --fixtures fixtures/synthetic-v1 --report build/reference_report_post_review.json

结果：
- 34/34 项测试通过，无跳过；完整输出 build/unittest_post_review.log。
- 54/54 样本通过：27 个 float32、27 个 int32，共 162 项数值比较。
- 报告 build/reference_report_post_review.json 记录修复后源码指纹。
  pre_review 与较早 final 报告保留为过程记录，不作为修复后的最终证据。
- 另做 546 次内存内元数据类型扰动检查，542 次被明确拒绝，
  4 次是合法变体，无未归类异常；该检查不是形式证明。
- 现有冻结样本未改写。未修改其他项目，未暂存、commit 或 push。

### 延期 Minor（历史记录；S1 已修复）

compare_arrays 直接接收零维 ndarray 且数值不同时，会正确返回 passed=false、
mismatch_count=1，但 first_mismatch 为 null 而非零维坐标 []。
fixture-v1 只允许 1—4 维，故冻结样本及本轮工具链不受影响。
后续在比较器接口收口时明确拒绝零维或补充坐标表达。

S1 更新：工具 0.1.1 保持零维比较输入兼容，失败坐标修复为 []，成功仍为 null。
上述内容保留为历史记录；修复与当前验收证据见 s1_validation_report.md / phase1a_baseline.md。

### 审查范围说明

共享输入验证/输出转换是刻意的边界，算术路径仍独立；本次共同转换缺陷已由
手工边界回归补足。FP64 归约差异按已冻结容差判定，哈希只做对应/损坏检查。
生成中断可能留下不完整目录，读取拒绝，重试使用新目录。
并发修改输入文件、真实模型、C/RTL/硬件、设备性能仍需后续专项验证。
