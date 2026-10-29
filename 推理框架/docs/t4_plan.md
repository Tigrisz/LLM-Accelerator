# T4 RV32交叉构建与最小静态链仿真计划

历史计划：以下设计/裁决和结果记录初次T4当时状态，不是当前状态入口。后续[T4D定位](t4_dual_debug_report.md)解释了原Verilator异常，[T4收尾](t4_closeout_report.md)汇总当前配置字段和验证；原始build报告/基线保持。

2026-10-26，用户授权准备目标工具链、交叉编译/仿真、ABI/布局/栈证据；目标未测项仍未知，PC/RTL仿真/实板分开，不绑定模型/W4A8。

## 设计与验收

- 固定xPack GCC15.2.0-1 Linux x64官方发布包及SHA256，本地build缓存中解压，不全局安装/更改PATH。记录可执行文件/库/版本/multilib/预定义宏与实际链接。
- 初次T4核对并固定主仓库c1bc715提交。采用已核对的完整generated/qinglong_all.sv经Verilator执行真实CPU/SoC RTL，保持64KiB TCM、原ISA和MMIO；不改上游RTL以迁就固件。
- 最小合成四节点链，offline IRS4BIN1导出，RV32固件仅绑定caller-owned元数据/arena执行；先整数路径，浮点/库仅有证据才扩展。
- 新裸机入口/链接脚本明确text/rodata/data/BSS/8KiB栈，保留map/readelf/attributes/nm/disasm/.su；ABI2由RV32探针核对，禁误用LP64/C/F/D/A/V。
- 无设备后台访问的CPU/TCM同步与恢复须明确；不可用时间/profile诚实报告，不伪造目标clock/fenv；读入只采用嵌入小blob，不宣称SD/DDR/DMA已实现。
- 负控覆盖短图/不足元数据、错误期望值或模拟失败不得通过；权重CRC正向检查，输出/完成节点/资源生命周期与参考对齐，timeout/工具失败保留未知。

## 任务

- [x] 1. 固定工具链来源、下载/校验/限定解压，检查RV32 multilib和库；源码快照/工具身份门禁先RED。
- [x] 2. 最小target harness、startup/linker与RTL仿真器；正常/零输入及错误路径，对比Python参考，PC完整C回归待最终副本。
- [x] 3. ABI与链接布局/逐函数栈帧/可获得的仿真高水位；明确哪些是确定布局、哪些仍非最坏峰值/实板证明。
- [x] 4. 当前PC基线/工具回归与新干净副本RV32入口，一次只读独立审查，必要修正后最终复验。
- [x] 5. 文档/状态差距清单与本轮来源/代码/工具/结果指纹收据；不覆盖旧T1—T3证据。

## Review Focus

1. 工具/库实际RV32 ILP32、小端、无不支持指令；工具名称、build成功和实际仿真通过必须区分。
2. 测的是主仓库固定RTL而非假CPU；正确result/completed/退出，trap/timeout/错误期望值不能当pass。
3. 测量地址/元数据/栈/镜像不重叠；.su不是运行最坏峰值，canary不冒充所有路径/ISR。
4. 不隐式伪造fenv/clock/同步、禁malloc；profile不可用不能声称完整追踪。
5. 下载校验、解压边界、产物绑定及历史指纹保护；所有未知明确，不把PC预算迁入目标。

## 执行记录

- Ruling: 用户已授权T4，指定目录原地实施，不另问方案/安装批准，不全局安装、不触碰兄弟项目、不提交/推送；工具下载仅受控目录内可恢复副作用。
- Ruling: 优先主仓库RTL仿真，QEMU即使可用也不能替代自研CPU集成结论；实际实板仍不验证。
- Ruling: 同一ELF对照确认单发射通过、默认双发射trap。采用现有参数DUAL_ISSUE=0完成最小链验证，额外保留默认DUAL_ISSUE=1诊断；不改RTL、根因不猜测。代价是不能宣称默认配置集成成功，后续正式集成须先定位故障。
- Ruling: 仅运行INT32最小合成链；现有核心带FP32分支，因此链接真实Newlib/libgcc软件浮点，fenv来自库，不自行伪造。时间/profile明确不可用，TCM同步真实fence；代价是FP32/时间追踪/设备DMA能力不在本次验证结论内。
- TDD: 证据测试先缺失模块RED，后补ISA属性检查RED，当前6/6 GREEN。实际错误期望固件退出10、watchdog未完成；异常不得通过门禁。全量与审查待后续记录。
- 独立只读审查：0 Critical、2 Important、1 Minor；原初验PC干净副本174+33项、资源验收通过，RTL干净副本复现单发射通过/默认失败。审查后源码变更，必须重新全量验收，不沿用旧快照作为最终结果。
- Final: Ruling: 将“未done的已观察trap/栈违规仍归未知”从Minor重评Important，因为会丢失已确认目标故障；与两项Important同轮修复。代价是仅有纯超时/工具失败才保留null，异常根因仍不推断。
- Final: fixed 工具链复用身份范围 — 新test_reused_toolchain_is_checked_against_archive_not_only_driver RED→GREEN；每次执行从SHA固定的官方包派生全部文件/链接指纹并逐项比较，拒绝额外文件，覆盖实际编译后端/工具/头文件/specs；代价为额外完整包/安装读取。
- Final: fixed 负控无关失败误判 — test_negative_controls_reject_crashes_traps_and_missing_summaries RED→GREEN；错期望须退出10无trap、watchdog须完整摘要及恰好10周期/预期退出1，崩溃不得替代。
- Final: fixed 已观察异常分类 — test_unproven_is_not_a_confirmed_target_failure 扩展trap/stack且未done反例RED→GREEN。修正后专项8/8通过，最终整套回归待执行；不重复独立复审，无延期小项。
- Final: 审查修复后PC干净副本完整174+35项，无跳过；54样本、双类型链×两种输入、24压力、200轮/2400任务、40分配故障、6原生含3 sanitizer通过。`build/t4_pc_final/report.json`。
- Final: 审查修复后RTL干净副本288源/数据文件、无旧build，真实官方包6159文件/链接身份比对通过；重新交叉编译/链接/仿真确认单发射正常/零输入、负控、ABI/布局/观察栈752字节；默认双发射相同ELF继续trap。`build/t4_clean_final/report.json`；完整最坏栈、FP32目标执行、实板仍未知。
- Final: 原地保存用户指定交付物，不合并/推送/删除工作目录；旧证据只核对不修改。最终收据`build/t4_baseline.json`及`.sha256`，完整性`build/t4_final_integrity.json`；晚于运行的三份收尾文档单列。
