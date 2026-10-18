# 验证基线、协议检查和持续集成

本轮以 GitHub main 提交 `1ae1c7798f06c6f35ec6ed57ea130aa38f374f70` 为基线。
该版本拆分了 activation_cache 的 read_i/load_i。修改测试前，已实际运行原有
test-b-vectors、test-integration、lint、lint-integration，全部通过。
不再按原定两周计划衡量完成度，按依赖和验证证据推进。

## 本轮完成内容

- 核心及集成测试共用独立 StreamMonitor：检查跨周期的 valid、完整 payload、标签和标记。
  前一周期阻塞后，即使本周期 ready 恢复，也必须保持原数据直到成功握手。
- GroupMonitor 检查每组接受的 beat 数、组首/尾位置、组内 row/group 标签一致性。
  这是仿真协议检查，不是给硬件增加非法输入错误响应的承诺。
- 检查器自测注入 21 种非法行为并确认拒绝，同时验证合法停顿、无效载荷和复位。
- 16 路新增 19 个、32 路新增 11 个定向测试：组内每个位置的复位与重启、
  各个 beat 前的 257 周期输入空闲、513 周期输出阻塞、阻塞后的恢复。
- 原来的 139 个功能用例、所有乘法组合和 B 的 107 个用例保留。
- Python 测试入口运行仓库全部 test_*.py（当前 21 项），包括 B 原有测试；空集合直接失败。
- 必需 B 向量缺失时失败，避免只用新生成的随机数据掩盖交付文件遗漏。
- 任一核心/集成仿真失败时，保存原始日志、命令、工作目录、超时信息，并自动带 TRACE_FILE 重放一次。
  重放即使成功，也不会把原失败改为通过。
- 故意改错一个 Golden 值，确认真实 Verilator 仿真失败且自动生成有效 VCD。
- 本地与 CI 共用 run_regression.py；记录 Python/NumPy/Verilator/G++、提交信息和测试源码 SHA256。

## 使用方法

在仓库根目录使用已有 Python 虚拟环境：

```bash
python scripts/run_regression.py
# 或
make regression PYTHON=/path/to/venv/bin/python
```

独立工作副本位于 Windows 项目下 development/；在 WSL 中可执行：

```bash
cd /mnt/d/Users/zhang/Documents/ChatGPT/嵌赛/development
source /home/tigris/projects/llm-fpga-accelerator/.venv310/bin/activate
python scripts/run_regression.py --base-revision 1ae1c7798f06c6f35ec6ed57ea130aa38f374f70
```

`--base-revision` 标记开发起点，不能冒充本轮修改后的提交号。
GitHub 执行记录实际 GITHUB_SHA；本地无 Git 历史的快照以源码 SHA256 为精确依据。
报告在 build/reports/environment.json、summary.json 和各阶段 .log 中。
失败文件在 build/failures/；故意制造的预期失败在 build/probes/，两者分开。
VCD 生成失败不会被伪报为已生成，实际结果在 reproduce.json 的 trace_created 字段。

## CI

.github/workflows/rtl-regression.yml 在 PR、main/codex 分支推送和手动触发时执行。
Ubuntu 22.04 与 24.04 分别使用发行版 Verilator，Python venv 固定 NumPy 2.2.6。
运行严格 lint、Python 测试、监视器自测、核心 RTL、Golden 交叉验证、真实失败重放和完整集成 RTL。
成功和失败均上传报告；失败时连同重放波形和向量夹具一起上传，保留 14 天。
最终云端结果见本轮合并请求的 Checks，不能仅凭 YAML 存在宣称 CI 已通过。

## 下一步与依赖

本轮没有改动 GEMV 数值数据通路、V1 接口或存储协议，B 不需要重新生成现有向量。
下一阶段可实现固定 128-bit 存储接口到 16 路核心的完整配对适配；需先与 B 约定适配模块边界。
B 可并行推进任务控制器和真实模型切片。
在收到 FPGA 型号、目标频率和综合工具前，不凭仿真周期推断板上频率或资源收益。
