# 初次T4验证记录（历史）

日期2026-10-26。本页记录初次T4当时使用原始RTL/Verilator5.032的验收，结果和指纹为`build/t4_validation_final/report.json`、`build/t4_baseline.json`及对应`.sha256`。后续T4D已定位该受测生成模型的更新排序问题并验证兼容方案，见[T4D历史定位](t4_dual_debug_report.md)；当前单/双配置及字段契约见[T4收尾](t4_closeout_report.md)。本页历史数字和旧build快照不代表当前兼容方案失败。

## 初次T4已核实结果（历史）

初次T4的工具链准备、ABI/ELF门禁、最小四节点INT32链**单发射RTL仿真通过**。当时原始RTL/Verilator5.032双发射执行同一ELF失败，`all_profiles_passed=false`、`deployment_ready=false`、实板未验证。该阶段通过限定于`verification_target=minimal_single_issue`；后续兼容方案的single_and_dual_issue另有证据。

最终PC证据：`build/t4_pc_final/report.json`；最终RTL证据：`build/t4_clean_final/report.json`，实际ELF/map/readelf/nm/objdump/`.su`及UART摘要在其`workspace/build/target/`内。两份干净副本各288个源/数据文件，初始无build，运行前后源与副本指纹一致；显式复用的只有受控工具链依赖，没有旧运行时二进制或仿真器产物。

PC：174/174原测试、35/35工具测试，均无跳过/错误/失败；54/54冻结样本、INT32/FP32双链×正常/零输入四记录，24资源压力探针、200轮、2400成功任务、40分配失败扫描位置，6原生执行（含3 sanitizer）通过。T4专项8项包含在35项工具测试内。T2历史审计仍54项/13未知，不回写历史证据。

工具链收据`build/t4_toolchain/install/receipt.json`；最终执行前对SHA固定官方压缩包与安装的6159个文件/链接完整比较通过，内容清单SHA256 `c612253b6bbacdc98b0c10a7cb3dac1ce43c5019ddc2ab46e92f610c3070c28e`。不仅比较gcc驱动和三库。锁定包和安装为显式外部依赖，不声称跨环境二进制逐字节可复现。

| 证据 | 已核实结果 | 边界 |
|---|---|---|
| 工具链 | xPack15.2.0-1/GCC15.2.0，包SHA固定，实际rv32im/ilp32库 | 本地受控安装；不宣称原主仓库既有工具已统一 |
| ABI | ELF32、小端、ILP32/soft float，栈对齐16，native ABI2/core ABI1 | 无C/A/F/D/V；FP32仅库链接，未目标计算验证 |
| RV32结构 | context144、tensor96、call32、profile32字节，对齐8 | 当时受测编译器/头文件/选项测量；PC context200字节属于另一平台 |
| 本链存储 | state9、临时inspect36、activation128、workspace64字节；9tensor/4node | 只对本次合成描述，容量上限仍4096/1024 |
| 链输出 | 正常`[20,-25]`，零输入`[0,-5]`，4节点完成 | 与独立scalar/NumPy参考一致；无具体模型 |
| 错误控制 | 短描述/不足inspect/state拒绝；错期望值退出10；watchdog不完成 | 完整目标错误路径尚未穷举 |
| 同步/时间 | publish/acquire各2次fence；时间和profile不可用标志0 | CPU/TCM同步，不代表DMA/cache/完整目标追踪 |
| 链接布局 | text/rodata30640字节；BSS`[0x77C0,0x7D60)`1440字节；栈`[0xE000,0x10000)` | 64KiB独占测试TCM；空隙25248字节不当作目标预算 |
| 栈证据 | 仿真最小sp64784，观察752字节；无越界/未对齐 | `.su` inspect144、bind304、main224字节为逐函数；最坏调用链/ISR/实板峰值未知 |
| 默认双发射 | 同ELF实际trap，PC0x264c/cause5，退出133；对应`irs_crc32`内`lbu` | 根因未知；定位到指令不等于定位到故障原因，未改上游RTL |

以上数值已由最终正常ELF核实；SHA256 `18c4029261ed0d0b0988089a3724405b029986a74992964af153116962fa76b0`。单发射644044周期完成正常/零输入；错误期望值固件实际退出10、无trap/栈违规；watchdog实际在10周期结束、done=0、退出1、无trap。报告保留全部命令与stderr，不从PC默认预算推导目标资源。

## 复现与兼容性

见[完整操作与边界](rv32_bringup.md)、[计划/执行裁决](t4_plan.md)。新增target harness和工具，原运行时/数值核心、冻结109文件/54样本及原174测试不作修改；PC入口不隐式下载工具链或运行沉重RTL仿真。T4新增工具格式v1，不更改runtime/native/wire/callback版本。T2来源及T3历史报告按当时事实保留，T4是独立受测配置证据。

## 初次待验证项与后续变化

默认双发射异常当时未定位，后续T4D已形成首次差异/生成模型排序/最小复现/Icarus反证及本地兼容改写验证。原主仓库应用/OS整合、正式工具链选型统一、板级最终可用内存图/栈额度、完整最坏栈、FP32目标数值、真实读取/时钟/追踪、DDR/DMA/cache/中断及实板仍未验证。54样本/双类型链/压力结果属于PC，不能升级为全部RV32通过。不绑定具体模型或W4A8，不提交/推送。

## 独立审查

一次全范围只读独立审查完成：0 Critical、2 Important、1 Minor。两项Important分别为复用安装未覆盖cc1/binutils/headers/specs，以及负控可能接受崩溃或无关trap；新增反例先RED后GREEN。Minor为已观察trap但未done时误归未知，因影响故障证据分类，实施者重评为Important并在同一修复轮覆盖：trap/栈违规不依赖done判失败，普通超时仍null。修复后8/8 GREEN及上述全回归通过；未进行第二次独立复审，无延期小项。

审查不判断默认双发射根因、不代替最终副本执行，也不证明最坏栈/ISR/FP32/DDR/DMA/cache/实板/正式OS预算；这些限制沿用上述未知。审查与修复记录`build/t4_review.json`。

## 封存规则

`build/t4_finalize.py`重新核对两份完整报告的所有产物、受测源快照、官方工具包SHA、冻结109文件、原174测试清单/源码、原C数值核心与T3静态运行时，以及S1—S6/T1—T3的旧收据/证据。结果为`build/t4_final_integrity.json`。最终运行后只收尾本页、T4计划和progress三份文档；最终源指纹与两份受测快照分别记录，不能把文档差异隐藏成同一份快照。工具包安装不重复纳入巨大证据目录，保留官方包SHA、逐项核验清单摘要及工具/库指纹。
