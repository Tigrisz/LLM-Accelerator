# A/B 计算流接口 V1（已对齐 B 发布版本并通过联调）

2026-10-17：以 B 仓库提交 `d8398373d69dd371df55ec7b69df46d7db10b9b7`
发布的 V1 协议为依据，端口及数据语义一致，完成实际 RTL 联调。
B 原始协议保存在 `docs/b_delivery/interface_v1.md`；本文件是 A 侧实施摘要。

## 数学与数据布局

`W[N,K] * X[K]`，按行、组顺序处理，固定 `GROUP_SIZE=128`。
权重为二补码 signed INT4，激活为二补码 signed INT8。
每个 `{row_id, group_id}` 输出一个 signed INT32 整数部分和；缩放由软件完成。

`LANES` 支持 16/32，默认 32。第 i 路位于
`weight_data[4*i +: 4]`、`activation_data[8*i +: 8]`。
每字节低 nibble 是前一个权重，高 nibble 是后一个权重。
32 路每组 4 beat；16 路每组 8 beat。
B 负责尾组补零，始终发满 128 个元素；同一输入向量供各输出行重复使用。

## gemv_core 端口（已实现）

| 方向 | 名称 | 位宽 | 含义 |
|---|---|---|---|
| 输入 | clk / rst_n | 1 / 1 | 上升沿时钟、低有效异步复位 |
| 输入 | in_valid | 1 | 本 beat 有效 |
| 输出 | in_ready | 1 | 核心可接收 |
| 输入 | weight_data | LANES*4 | 已打包权重 |
| 输入 | activation_data | LANES*8 | 与权重逐路对齐的激活 |
| 输入 | group_first / group_last | 1 / 1 | 分组首尾 beat |
| 输入 | row_id / group_id | 16 / 16 | 同一组内保持一致 |
| 输出 | out_valid | 1 | 结果有效 |
| 输入 | out_ready | 1 | 接收端可接收 |
| 输出 | partial_sum | signed 32 | 当前组整数部分和 |
| 输出 | out_row_id / out_group_id | 16 / 16 | 结果标签 |

## 握手与复位

- 只在 `in_valid && in_ready` 的上升沿消耗输入；组标记也仅在该时刻生效。
- B 在 `in_valid && !in_ready` 时保持全部输入载荷及标记稳定。
- A 在 `out_valid && !out_ready` 时保持结果与标签稳定。
- 同一组不得与其他组交织。组首清除上一组累加，组尾包含当前 beat 的乘积。
- V1 允许组间停顿，不承诺每周期可无间隙接收；B 不得假定固定 ready。
- 复位撤销所有未完成输入组和待接收输出，恢复 `out_valid=0`；B/控制器同步取消任务并重新开始。
- V1 假定组序列合法；非法 N/K/地址由 B 的控制器检查，核心仿真检查组协议。
- 核心没有 start/done/DDR/AXI 端口；系统 done 应在最后结果成功握手后产生。

## 已接收的 B 交付与后续依赖

1. B 已发布上述 packing、首尾标记、标签、补零及复位语义。
2. 已接收并验证 N=1,K=128；N=3,K=256；N=2,K=129 三个指定向量，以及 case_001。
3. 文件为 config.json、weight_packed.bin、activation_int8.bin、expected_partial.npy、stream_reference.json。
4. expected 形状为 `[N,ceil(K/128)]`；权重逐行补零，激活文件长度为 padded_K，不能仅加载逻辑 K 字节。
5. load_valid_elems 只统计逻辑有效元素；K=129 时仍须装载 8 个 32 路 beat，计数依次为 32/32/32/32/1/0/0/0。
6. 后续仍需要真实模型权重切片与 CPU BFM/控制器。

## 实现状态

已实现解包、单路乘法、16/32 路并行归约、分组累加与流接口。
已通过 B Golden 的 16/32 路核心测试，以及默认 32 路完整存储链路联调。
16 路完整链路仍需要固定 128-bit 存储 beat 到 64-bit 核心 beat 的拆分适配；本次未实现。
真实模型切片和 CPU/MMIO 联调尚未完成。
