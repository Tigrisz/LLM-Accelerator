# A：W4A8 GEMV 计算核心

本目录是 A 的计算模块及 A/B 联调工作目录。接口见 `docs/interface_v1.md`，已对齐 B 发布的 V1。
默认 LANES=32，也测试 LANES=16；固定分组 128 元素，输出 signed INT32 部分和。

## 运行

在 WSL Ubuntu 中执行（Windows 共享目录映射）：

```bash
cd /mnt/d/Users/zhang/Documents/ChatGPT/嵌赛
mkdir -p build
make test-compute lint
```

已用 Ubuntu-SRTP 的 Verilator 4.038、G++ 和 Make 验证。
当前采用 C++ 驱动 Verilator，不依赖 cocotb，也不要求 NumPy 即可运行核心回归。
Python 3.10/NumPy 环境用于后续读取 B 的 `.npy` 标准答案。

## 模块

- `int4_unpack.sv`：打包 nibble 转 8 位符号扩展的辅助模块。
- `mac_lane.sv`：signed INT4 × signed INT8，输出 signed 12 位乘积；累加在独立模块。
- `gemv_core.sv`：逐路提取 nibble，经 mac_lane 符号扩展/乘法、平衡加法树求和。
- `group_acc.sv`：组累加、单项输出寄存器、ready/valid 反压。

组尾在输入成功握手的上升沿产生输出，消费者最早在下一个上升沿接收。
输出未接收时整个输入被反压；接收旧输出的同一周期可接收新输入。
无停顿时可每周期接收一个 beat；输入标签在组内须一致，首尾标记由 B 生成。
没有额外流水级；未做厂商综合，不承诺实际 Fmax 或资源用量。

## 验证范围

每种并行度穷举全部 4096 种单乘法输入；验证全部 16 种 nibble 在各 lane 的解释。
核心每种并行度执行 139 个功能测试及一次独立无停顿周期测试：

- K=1/32/127/128/129/255/256/384/2048，多行多组。
- 随机、全正极值积、全负极值积、全零权重。
- 100 个固定随机种子的连续任务数据流（不复位地串接合法分组）。
- 随机输入空闲、输出反压、20 周期输出阻塞，稳定保持待发送输入。
- 空闲复位、半组复位、待接收结果复位，检查残留累加/输出清除。
- 每个输出数值及 row/group 标签逐项核对；超时、重复/缺失/乱序输出会失败。

参考答案在 C++ 中使用解码前的有符号整数精确求和，独立于 RTL。
上述为最初的独立核心回归；新增 B Golden 与存储链路回归见下方。
N/K 配置合法性、busy/done、地址错误和存储协议属于 B 的控制/系统联调。

## 波形及失败复现

构建测试后：

```bash
TRACE_FILE=build/core32.vcd ./build/core_32/Vgemv_core
gtkwave build/core32.vcd
```

失败会报告并行度、随机种子及周期；测试种子固定，重复上述命令可保留波形。
查看 clk/rst_n、in_valid/in_ready、group_first/last、out_valid/out_ready、partial_sum 及标签。
VCD 时间单位为测试驱动的采样步，性能指标只使用明确计数的时钟周期。

## 交给 B

请发送 `docs/b_handoff_2026-10-17.md`、`docs/b_memory_fixes.patch` 和交接压缩包。
当前进度、修复及后续分工见交接说明。

## 2026-10-17：B Golden 与存储链路联调

B 来源：`https://github.com/Tigrisz/LLM-Accelerator`，提交
`d8398373d69dd371df55ec7b69df46d7db10b9b7`。
`model/` 和 `tests/vectors/` 继承 B 的交付；`rtl/memory/` 包含已验证的必要修复。
原始 B 文档归档在 `docs/b_delivery/`。`upstream-b/` 是本地对照下载，不参与构建，也不进入交接包。

```bash
cd /mnt/d/Users/zhang/Documents/ChatGPT/嵌赛
source /home/tigris/projects/llm-fpga-accelerator/.venv310/bin/activate
make test-b-vectors        # 原有核心回归 + B Python 测试 + B Golden 16/32 路交叉验证
make test-integration     # 32 路 B 内存/reader/cache/配对器 + A 核心
make lint lint-integration
```

其他机器可用任何装有 NumPy 的 Python 3.10+，例如 `make test-integration PYTHON=/path/to/python`。
Verilator/G++/Make 仍为必需。所有 build 目录由 Makefile 创建。

新测试读取实际 `.bin/.npy/.json` 文件，先核验 B Golden 和流元数据，再转换为仿真器文本夹具。
包含 4 组 B 交付数据、100 个固定种子随机矩阵，以及 K=2048/6144/8192 三组长向量。
核心测试对 16/32 路分别测试连续/随机停顿；完整链路默认 32 路，内存延迟 2、LFSR 随机停顿。
每个链路用例连续执行两次任务，并有末尾结果 20 周期反压，检查 done 不提前。
另检查缓存容量边界、未对齐/越界地址、N/K=0、处理中/待输出复位及重新启动。

`tests/tb_b_integration.sv` 是联调夹具：主机直接装载模拟内存和激活缓存，自动逐行重放激活。
它尚不是第 8 天的寄存器/MMIO/CPU BFM。夹具的配置在任务期间保持稳定，只在空闲且缓存已加载时启动。
`reader_done` 表示输入读取结束，夹具 `done` 以最后结果成功接收为准。

```bash
TRACE_FILE=build/b_integration.vcd ./build/integration/Vtb_b_integration build/b_fixtures/case_n2_k129.txt
gtkwave build/b_integration.vcd
```

所有测试向量目前都是合成整数数据，长 K 用例也不是 Qwen 真实切片。
输入等待统计包含缓存/存储/配对等待，不能直接叫作 DDR stall 或实测 GB/s。
