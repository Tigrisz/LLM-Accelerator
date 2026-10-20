# A/B 合并说明与上板进度核验

## B 的交付与证据边界

B 提交 `90d198f` 增加 Qwen2.5-1.5B-Instruct 切片提取脚本、16×128 固定切片 ROM、
板端自检 runner、16/32 路寄存器控制封装、PDS 工程、约束和位流。
所选层按脚本默认值为 layer 0 self_attn.o_proj。提交的 mem 可独立验算，但仓库缺少
该次提取的模型 revision、完整 config/scale 元数据，不能仅凭 mem 追溯具体 checkpoint。

上传的 PDS 记录显示：

- 目标约束为 MES2L676-100HP / PG2L100H-676，时钟 27 MHz。
- 时序摘要 All Constraints Met；慢角 setup WNS=24.349 ns，快角 hold WHS=0.109 ns。
- 布局布线模块资源统计：354 LUT、185 FF、16 APM、2 DRM。
- 位流生成成功；configuration.log 在 2026-10-20 01:17:01 记录 Program 成功及 done bit=1。

这些是 B 上传的工具记录，本次未重新运行 PDS。配置 done bit 不是计算 done/pass。
还需 B 提供板上 led_done/led_pass/led_fail 的实际状态，最好附复位重跑记录或输出读回。
固定切片使用 ROM 与片上比较，不等于 DDR/CPU 全链路或完整模型推理完成。

## 合并策略

PR #4 包含 PR #2、#3 的全部提交。在 #4 分支合入最新 main，再处理冲突、执行完整回归，
最后以 merge commit 合并 #4，保留各分支祖先关系。不要依次覆盖文件或手工复制历史版本。

- 合并 Makefile，保留 A 的全部测试、性能比较，以及 B 的控制与固定切片目标。
- 同名测试拆开：B 保留 `tests/test_lane_adapter.cpp`，A 改为 `tests/test_paired_lane_adapter.cpp`。
- B 的 `lane_adapter_32_to_16` 有数据寄存器，由控制/板端路径使用。
- A 的 `paired_lane_adapter` 保持上游拍直到两半被消费，由 A 联调/基准路径使用。
  两者名称与构建入口独立。本次不更换已生成位流所用的适配器。
- 因此先前 A 性能表不能当作 B 固定切片板端的测量结果。
- PDS source 顶层相对根目录顶层，只修改 mem 路径并移除对外调试计数端口；
  核心、累加器、B 适配器、runner 等源码核对一致。保留 PDS 工程快照原样。

## 验证入口

```bash
python scripts/run_regression.py
```

完整回归扩展为 15 阶段，包含 A 原有回归、两种并行度基准，及 B 的适配器、
16/32 路控制接口、合成固定切片、上传 Qwen mem 固定切片仿真。
`scripts/verify_board_mem.py` 先从十六进制文件独立解码有符号 INT4/INT8，重新计算全部
16 个 INT32 点积，比对 expected.mem 后才复制到 build/fixed_slice_qwen 供仿真使用。
该步骤不下载模型，也不需要 torch/transformers。
最终结果以 CI Checks、build/reports/summary.json 和 board_mem.json 为准。

## 下一步

1. B 补实际板上 pass/fail 观察、复位重复运行证据，并保存对应位流/输入哈希。
2. A 准备板端输出比对工具：核对 row/group、INT32、缺失/重复结果和首个不一致位置。
   目前板端顶层只有 LED，没有逐行输出端口，需与 B 对齐 UART/JTAG/寄存器读回方式。
3. B 补切片来源及量化 scale 元数据；先固定当前 16×128 切片，再扩大到多组 K。
4. 多组调度与反量化验证完成后，再评估真实内存接口性能、预取及更大矩阵。
