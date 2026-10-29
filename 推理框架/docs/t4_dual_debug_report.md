# T4D历史记录：默认双发射异常定位与本地兼容改写

2026-10-26，本阶段采用模型无关的INT32合成链，runtime0.6.0/native ABI2/core ABI1未改。原始主仓库RTL固定c1bc715，原完整ELF SHA256 `18c4029261ed0d0b0988089a3724405b029986a74992964af153116962fa76b0`。

本页记录T4D定位验收的历史执行（301源文件、174+39测试、80次矩阵）。当时延期的参数汇总/历史措辞两项已在后续[T4收尾](t4_closeout_report.md)关闭；当前报告v2增量rtl_profiles/v1的双配置契约和新回归以该页为准，旧build报告和审查JSON不回写。

## 已确认的定位链

1. 同一完整ELF在原始Verilator5.032模型单发射通过、双发射于CRC的PC0x264c/cause5（trap_value=0x10000）失败。它是后果，不能把CRC函数当成根因。
2. 第一处架构写回差异为退休序号1522，`memcpy`的`andi a2,a2,-4`（PC0x3f18）。正确结果0x14，原双发射结果0xff94；它与前一条`sub a2,a2,a4`被错误配对。
3. 预发射日志cycle1553：FIFO头sub元数据0x47，第二条andi元数据却是0（应0x46）；pair_swapped=1，RAW/WAW检查遗漏。原Verilator生成C++中metadata的追加更新在压缩更新之前应用，后者覆盖前者；同槽PC/insn仍追加优先，发生错位。这里确认的是受测版本生成模型的排序行为，不概括所有版本/RTL写法。
4. 独立Icarus使用**原始RTL和同一完整ELF**默认双发射通过，445747周期，正常`[20,-25]`、零输入`[0,-5]`。这直接否定“已证明CPU硬件双发射逻辑缺陷”的结论。
5. 提取56字节、无C库/模型/栈的RV32汇编例：初始化两个寄存器，跳转到`addi/sub/andi`依赖序列，再将计算与20比较并写done。原Verilator单发射退出0、双发射退出3，Icarus两配置均退出0。三条关键指令与完整ELF首差异一致。

两次更小FIFO归约在两仿真器均通过，未独立复现完整CPU的编译调度条件；保留为对照，不把它们当作RED证据。RED证据是完整CPU+56字节ELF，以及原始完整ELF。

## 修复方式与归属

`tools/rv32_rtl.py`在核对归档SHA/commit后生成本地选择副本：两个纯组合`issue_metadata(response_dec*)`先接wire，时钟进程中FIFO追加写入这些wire。只做三处锚定替换，缺失/重名锚点拒绝应用；原始归档不修改。输出`compatibility.patch`可审查。

这是一项保持意图语义的仿真兼容改写，没有关闭双发射、插软件nop、改ELF、改编译器参数、硬编码CRC或结果。`rtl_selection`区分upstream_sha256/selected_sha256、mode/local_overlay，上游仓库没有合入此改写。形式等价、综合/PDS时序及实板仍未验证。

主入口`run_rv32.py/reproduce_rv32.py`工具报告升级v2，默认portable-metadata必须通过单发射和双发射正常/零输入、错误期望退出10和watchdog控制；upstream模式保留原单发射范围及默认失败诊断。runtime/wire/回调ABI不变，部署标志仍false。

## 复现

在具备原T4受控工具链、Verilator5.032、Icarus、Linux/WSL/NumPy的本目录运行，输出目录必须不存在：

```sh
python3 -B tools/validate_dual_issue.py --toolchain build/t4_toolchain/install/xpack-riscv-none-elf-gcc-15.2.0-1 --elf build/t4_clean_final/workspace/build/target/normal/firmware.elf --output build/t4d_diagnosis_new
python3 -B tools/reproduce_rv32.py --toolchain build/t4_toolchain/install/xpack-riscv-none-elf-gcc-15.2.0-1 --output build/t4d_target_new
python3 -B tools/reproduce.py --output build/t4d_pc_new --iterations 200
```

第一条把封存ELF作为明确测试输入，严格要求上述SHA，不称“无历史输入”；源码/仿真器均重建。第二/三条才是源副本无历史build的当前运行时验收；第二条当前默认portable-metadata，可加`--rtl-mode upstream`重现历史。

矩阵入口对原/兼容RTL×单/双发射构建模型，在两仿真器执行原完整ELF、56字节最小例与8个RAW/WAW/寄存器/操作/值变体；记录全部命令、stderr、每个ELF/RTL身份及轨迹。正向完整轨迹必须没有截断，逐条比较PC/指令/rd/data。原Verilator双发射失败保留，其他受测正向路径必须通过。

## T4D阶段验证结果（历史）

审查修复后的最终交叉矩阵及PC/RV32干净副本均已通过。最终汇总`build/t4d_validation_final/report.json`，指纹`build/t4d_baseline.json/.sha256`，完整性复核`build/t4d_final_integrity.json`。

矩阵证据`build/t4d_matrix_final/report.json`：40个profile/case记录、80次仿真（10个程序：原完整ELF+56字节最小例+8变体）。原始失败是保留的反例，不能将整体验收通过描述成80次目标执行均成功。

| RTL选择/发射 | Verilator5.032正向成功 | Icarus正向成功 |
|---|---|---|
| 原始/单发射 | 10/10 | 10/10 |
| 原始/双发射 | 1/10，9个指定或算术失败保留；含完整trap与最小退出3 | 10/10 |
| 兼容/单发射 | 10/10 | 10/10 |
| 兼容/双发射 | 10/10 | 10/10 |

兼容单/双配置的完整轨迹各实际533119行，格式、序号、周期、寄存器和计数校验通过，逐条PC/指令/rd/data与原始单发射完全一致。完整原双发射首差异签名仍为退休1522/0x3f18/0x14→0xff94，最后trap264c/cause5/value10000；最小例退出3及关键算术写回均严格核实。原双发射大失败轨迹只保留前600000行，并明确截断；不称它为完整轨迹。另以`/dev/full`实际触发驱动写入/flush失败，退出2且无DONE摘要，拒绝把I/O失败当目标结果。

T4D当时RV32干净副本证据`build/t4d_target_final/report.json`：301个源/数据文件、初始无build、源与副本运行前后未变；重新交叉编译的正常ELF与原封存SHA完全相同。兼容单发射644053周期、双发射445747周期，正常/零输入输出正确、4节点完成；两配置错误期望值均实际退出10，watchdog均恰好10周期未完成且无trap。ILP32/小端/软浮点、ISA属性/nativeABI2/context144字节/布局不变；两配置观察栈均752字节，无栈越界/未对齐。该栈值仍只是受测路径高水位。

T4D当时PC干净副本证据`build/t4d_pc_final/report.json`：301个源/数据文件、无历史build；174原测试+39工具测试全过，无跳过/错误/失败，54样本、双类型四节点链×正常/零输入、24资源压力、200轮、6原生含3 sanitizer通过。当时运行时源、原测试及冻结样本与历史核对，不把PC覆盖升级为全部RV32覆盖。

一次独立只读审查完成，0 Critical/2 Important/2 Minor。两项Important已同轮新增3项测试RED→GREEN：严格指定故障签名；检查真实轨迹行数/格式/连续序号/周期/寄存器及写入flush/close状态，拒绝相同截断前缀或空文件。修复后上述最终完整复验已完成，不进行第二次独立复审。

T4D审查当时延期两项小项：legacy `verified_rtl_parameters`仅单发射、部分历史措辞待统一。后续T4收尾已新增rtl_profiles/v1按两配置汇总并标明legacy作用域，统一当前/历史文档；T4D旧审查JSON中的deferred_minors是当时事实，当前不再属于未完成项，具体新验收见收尾记录。

实板、形式等价、PDS综合/时序、其他Verilator版本、FP32目标计算、完整最坏栈/ISR、OS实际内存预算、目标时间/profile/完整追踪、DDR/DMA/cache/真实模型均未验证。不绑定具体模型或W4A8。

最终封存重新核对两份源码副本的全部产物、矩阵真实轨迹/指定反例、原174测试清单/源码、109冻结文件、原核心/T3静态运行时及S1—S6/T1—T4旧收据/证据。只对本文、计划和progress做晚于运行的结果收尾，受测快照与最终源指纹分列，不覆盖旧基线。无提交/推送，无上游修改。
