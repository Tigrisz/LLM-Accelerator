# A4 验证报告

日期：2026-10-24。范围仅本目录的最小 C 算子与同步调用链。

## 已完成

- C11 张量/算子 ABI，linear（可选 bias）、add、relu，FP32/INT32。
- 元数据、布局、容量、别名、工作区、padding 和数值检查。
- 单算子工作区暂存后提交；四节点顺序调用链和失败节点计数。
- Python 编译/绑定/54 样本及调用链比较；独立 C 直接测试和 ASan/UBSan。

## 测试先行

- 原 34 项 A1—A3 测试基线通过。
- 新 10 项 Python C 后端测试先因缺失实现失败。
- 直接 C 测试先因缺失核心源码编译失败。
- 实现后，WSL GCC 严格 C11 编译通过，新 10 项测试全部通过。
  其中已实际核验 54 个冻结样本、两条四节点链及原生 sanitizer 测试。

## 环境

PC：WSL Ubuntu x86_64，GCC 15.2.0，Python 3.14.4，NumPy 2.3.5。
主机沙箱内 WSL 调用受限；实际编译和执行通过获准的主机执行完成。
没有安装额外工具，没有以静态检查替代 C 执行。

## 边界

这不是完整模型推理、模型包加载器、通用图执行器或模拟设备队列。
未验证 RV32/FPGA、DDR、设备驱动、Windows 原生 DLL 或性能。
原 54 个样本保持不变，旧 Python 参考数值规则不变。
未提交、未推送；没有修改其他项目。

## 独立审查与修复

审查发现 1 项 Important、1 项 Minor；均已处理并只读复核，未留下新增阻断项。

1. completed_steps 与输入/输出/工作区/调用数组/张量描述符重叠时，原先会提前写入。
   五类别名回归先实际失败，再改为首次写入前拒绝，原内容保持。
   直接 C 测试也覆盖这些拒绝行为并实际运行 ASan/UBSan。
2. 原先链数值失败会抛异常中断报告。现在以状态和完成步数形成失败报告，退出码 1。
   注入 NUMERIC_OVERFLOW 的回归先复现异常，再验证真实生成 report.json 和 CLI=1。
   该注入只验证报告错误路径；真实 C 数值溢出另由直接执行回归验证。

## 最终验收结果

2026-10-24，在上述 WSL PC 环境执行修复后的完整回归：

| 验收项 | 结果 |
| --- | --- |
| A1—A4 完整 unittest | 46/46 通过，无跳过；运行 27.340 秒 |
| 既有冻结样本 | 54/54 通过，FP32/INT32 各 27 项 |
| 每样本对齐 stored expected / Python scalar / NumPy | 共 162 项比较全部通过 |
| 四节点 C 调用链 | INT32、FP32 各一条；均 OK、completed_steps=4 |
| 链逐节点和手算最终值 | 全部通过，最终 [20,-25] |
| 直接 C 测试 | C_CORE_TESTS_PASS，退出码 0 |
| ASan + UBSan | halt-on-error 开启，退出码 0，stderr 为空 |
| 源码与报告哈希 | C 源码和头文件匹配最终 build.json |
| 冻结样本保持 | 109 个文件的调用前后哈希一致回归通过；suite 和 54 个 manifest 哈希也与 A1—A3 报告相同 |

INT32 采用精确比较；FP32 按原规则 atol=1e-6、rtol=1e-5。
以上执行时间仅为测试运行记录，不作为算子或板端性能数据。

额外探索：审查前以固定种子 20261024 做过 200 个数值探针，全部与标量参考一致，
其中 50 个双方均拒绝数值溢出。此记录是补充证据，不替代修复后的正式验收。

## 可复查证据

- build/a4_validation_final/report.json：最终逐样本、逐节点、工具环境、源码和二进制哈希。
- build/a4_validation_final/backend/build.json、build.log、libir_core.so：实际编译产物。
- build/a4_validation_final/native_tests/result.json、build.log、run.log、core_tests：原生 sanitizer 证据。
- build/a4_unittest_final.log：46 项完整日志。
- build/a4_numeric_probe.json：上述审查前补充数值探针摘要。

重新运行请使用 c_backend.md 中的命令和一个不存在的新输出目录，保留既有验收记录。
A4 完成；A5—A7 尚未实现。既有比较器对零维 ndarray 首个差异位置的已知限制仍保留，
fixture-v1 禁止零维，故不影响本轮 C 样本链。
