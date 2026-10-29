# T5：冻结INT32样本RV32迁移验证

2026-10-26。审查修复后的最终PC/RV32干净副本验收已通过：27个原INT32样本全部完成，容量阻断0。原54冻结样本中FP32共27，标not_in_scope，不计为失败或目标通过。运行时0.6.0/nativeABI2/coreABI1/wirev1保持，不绑定具体模型/W4A8。最终汇总`build/t5_validation_final/report.json`，基线`build/t5_baseline.json/.sha256`，完整性`build/t5_final_integrity.json`。

## 路径

先同步S6能力文档；沿用原fixture→自有包→PC离线规划/IRS4BIN1导出，保持每个逻辑/物理shape和原输入字节。Python标量、独立NumPy、PC直接C和PC独立静态C先精确对齐；静态C物理输出同时验证padding。正向RV32固件只嵌入描述/权重/原输入/零输入，不嵌入golden；通过UART发出真实原始输出，PC端逐字节比较。

每例一固件，同一ELF直接供单/双发射；每例运行原输入→零输入→原输入，再执行同步未知/拒绝关闭和拒绝恢复/恢复后原输入、关闭重新绑定后原输入，共5次有效输出，另有一次执行完成但输出同步失败的未知结果，不导出有效输出。资源为调用方静态区，不声称完整目标分配器或DMA释放证明。

13组契约/生命周期检查：短镜像、CRC损坏、检查区不足、state容量不足、arena不足/未对齐、32位范围、绑定后输出无效、缺输入、错误输入长度、未重新供输入重复run、无效输出保护、同步未知/关闭与恢复保护、close/rebind。数学32位范围检查不是对0xffffffff真实访存。

另建合成add(INT_MAX,1)数值溢出探针，Python两参考与PC C均须拒绝，RV32检查status6/完成0/失败输出未提交/重新供零输入后恢复计算；它不是新冻结样本，也不是量化计算。profile与目标时间仍不可用。

## 容量与结果状态

容量按真实链接/map/ELF判断：64KiB测试TCM，栈预留[0xE000,0x10000)；静态段必须在栈下。仅明确容量诊断可标blocked_tcm；未解析符号/一般编译错误不能冒充容量阻断。另用真正65536字节静态段链接负控测试门禁，不改原样本形状。

冻结suite索引SHA固定为`f8420082c5b9680f942fbf7e3aba8292c114cc44fef10a4af3e0eb64b52fcb98`，与T4C旧基线核对一致。编译前必须验证全部54例/109文件、每份manifest/payload SHA和27/27类型分组；缺整例、改索引或空根均拒绝。逐tensor保真校验后才生成固件，不能只写shape_unchanged=true而无实际检查。容量分类拒绝信号崩溃、混合undefined reference或未知诊断，避免隐匿工具故障。

报告区分passed/blocked_tcm/failed/unproven/tool_error，blocked项passed=null、未执行目标；整体执行流程完成与全部选中样本已目标验证分开。每例记录原manifest/payload/shape/storage_shape、导出/ELF/map/属性/反汇编/.su、配置参数、真实stdout/stderr、PC参考结果和输出字节。输入冻结文件前后SHA必须一致。

## 复现

Linux/WSL，Python/NumPy、gcc/cc、Verilator和T4已准备的受控工具链。输出目录必须不存在：

```sh
python3 -B tools/reproduce_rv32_samples.py --toolchain build/t4_toolchain/install/xpack-riscv-none-elf-gcc-15.2.0-1 --output build/t5_samples_new
python3 -B tools/reproduce.py --output build/t5_pc_new --iterations 200
```

干净副本无旧build/ELF/仿真器，工具链是显式外部依赖，每次对照固定官方压缩包完整安装内容。主入口tools/run_rv32_samples.py；本轮沿用portable-metadata兼容RTL，原始来源/上游/T4旧基线不修改。

尚未覆盖FP32目标计算、真实模型、实板、PDS综合/时序、形式等价、其他仿真器版本、最坏栈/ISR、真实时间/profile、DDR/DMA/cache/OS资源。sp记录仅本轮路径观察值，TCM布局不是板端可用预算。

## 审查和初验

初验`build/t5_pre_review_v2/report.json`为27例通过、0容量阻断，额外数值溢出和真实超容量探针通过；初轮PC API适配错误已修复，不是CPU失败。之后一次独立只读审查0 Critical/2 Important/0 Minor，发现冻结样本缺失和混合链接诊断门禁问题，已同轮反例RED→GREEN修正，专项6/6通过，无延期，不二次独立复审。最终当前源码干净副本回归如下，不以初验替代最终证据。

## 最终实际结果

两份源码副本各312个源/数据文件，初始不含build，运行前后源与副本指纹一致。PC入口`build/t5_pc_final/report.json`，目标入口`build/t5_target_final/report.json`；每例包、导出、ELF/map/readelf/反汇编/.su、PC基准及UART stdout/stderr在后者`workspace/build/samples/`内。

| 范围 | 本轮实际结果 |
|---|---|
| 冻结清单 | 54例/109文件原指纹；选中27 INT32（24 linear、2 add、1 relu），27 FP32明确排除目标范围 |
| PC参考 | 每例正常/零输入经Python标量、独立NumPy、直接C、独立静态C精确相等，正常值另与冻结expected一致；物理padding字节与PC静态输出一致 |
| RV32正向 | 27/27全部通过；每例同一ELF分别跑单/双配置，共54个profile执行、270份有效输出逐字节对齐；failed/unproven/tool_error均0 |
| 重复/恢复 | 原→零→原、同步未知恢复后原、close/rebind后原五次有效输出；另54次同步失败后未知状态保护，均拒绝有效输出/关闭直到恢复确认 |
| 异常检查 | 每个profile均完成13组契约/生命周期检查；额外合成溢出两配置status6/完成0/输出未提交/重新供零后计算成功 |
| TCM | 原27样本blocked_tcm=0，未缩形/截断/换样本；65536字节额外静态区真实链接失败被明确容量门禁识别 |
| 布局/栈 | 初始化镜像30808—31288字节；最高BSS末地址32480，低于栈底57344；27样本两配置观察栈均816字节，无trap/栈越界/未对齐 |
| PC完整回归 | 原174/174＋工具50/50，无跳过/失败/错误；54样本、双类型四节点链×正常/零输入、24压力/200轮、6原生含3 sanitizer通过 |
| 实板 | 未验证，deployment_ready仍false |

816字节是本次T5测试固件路径观测，T4的752字节属于另一测试固件；两者都不是完整最坏栈。代码/库/常量/元数据均包含在每例实际map/ELF中，不把TCM空隙当真实模型或OS可用预算。没有新增FP32目标计算、FPGA加速器或真实异步后端验证。

`build/t5_finalize.py`封存前重新核对所有新产物与报告、每例原shape/storage/输入字节、PC物理输出、54份实际UART门禁、额外探针、原174测试/109冻结文件、C核心/静态运行时/T4启动链接与驱动/RTL选择源，以及S1—S6/T1—T4/T4D/T4C旧收据及全部旧证据。受测快照与最终源指纹分列，仅本文、计划和progress在运行后收尾，不覆盖旧基线。未提交/推送，原地保留全部交付。
