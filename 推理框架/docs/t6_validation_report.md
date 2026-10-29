# T6：冻结FP32样本RV32软浮点迁移

2026-10-26。审查修复后的最终PC、INT32、FP32三个干净副本验收通过：原27 FP32全部完成、TCM阻断0，INT32回归27/27。运行时0.6.0/nativeABI2/coreABI1/wirev1保持，不绑定具体模型/W4A8。最终汇总build/t6_validation_final/report.json，指纹build/t6_baseline.json/.sha256，完整性build/t6_final_integrity.json。

## 数值及软浮点契约

原FP32存储，提升为FP64计算；linear使用C有界展开/Python math.fsum，末端舍入FP32。明确不是FP32硬件逐次MAC。原comparison为abs_plus_rel，atol=1e-6、rtol=1e-5；检查真实shape、所有逻辑输出有限、物理padding保持初始化+0字节。逐位相同是单列指标，不能代替容差契约；同一ELF单/双发射及同输入重复/恢复输出另外要求逐字节相同。正常输出还直接比较冻结expected。

目标使用固定xPack15.2.0-1/GCC15.2.0，rv32im_zicsr_zifencei、ilp32、小端、soft ABI。核对编译宏、rv32im/ilp32 multilib、实际libgcc.a路径/哈希/安装完整性，链接的__adddf3/__subdf3/__muldf3/__extendsfdf2/__truncdfsf2等；ELF属性和反汇编检查未引入F/D/C/A/V。禁止fast-math、FMA融合。ABI是调用约定，是否有F/D指令还要核对march及实际链接产物。

来源：[GCC RISC-V选项](https://gcc.gnu.org/onlinedocs/gcc/RISC-V-Options.html)、[GCC软浮点运行库](https://gcc.gnu.org/onlinedocs/gccint/Soft-float-library-routines.html)，以及本地C核心/FLAGS/编译器与产物证据。文档只提供机制依据；实际舍入由严格输出探针核验，不推断完整IEEE754或动态舍入模式支持。

## 路径与异常

保留原54/109冻结集合和固定suite SHA；选择27 FP32，INT32不冒充本次FP32结果。逐tensor保留原shape/storage/dtype/layout/物理字节SHA；PC两条Python参考、直接C、独立静态C对照后导出原包，一例一ELF，供单/双配置。固件不嵌golden，UART发出真实输出供host比较。

每例原→零→原、同步未知恢复后原、close/rebind后原，共5份有效输出；另一次计算完成但同步失败的未知状态，禁止输出/关闭直到确认恢复。沿用13组短镜像/CRC/检查区/state/arena/32位范围/缺输入/错误长度/未重新供输入重复run/无效输出/同步未知/重绑定检查。

在冻结样本前另跑6元素add边界探针，手算bit pattern验证半偶舍入两侧、最小次正规相加、相消、接近FLT_MAX但可舍入为有限值。Python标量、NumPy、PC两C路径与两配置严格字节核对。另两元素add异常探针：NaN/±Inf在input处拒绝且输入保持；故意破坏调用方输入数据后numeric core再拒绝非有限；第一元素可算而第二元素溢出时全部输出保持0x5a、完成数0、无有效输出；重新供零后成功。额外探针不是新增冻结样本，也不是形状替代。

64KiB TCM/8KiB预留栈沿用测试布局，按真实链接/map检查；blocked_tcm仅用于明确容量诊断，工具错误/未知/数值失败分列。额外65536字节静态区真实链接负控验证容量门禁。不是板端OS/模型可用预算。

## 复现

输出目录必须不存在，在Linux/WSL运行：

```sh
python3 -B tools/reproduce_rv32_samples.py --toolchain build/t4_toolchain/install/xpack-riscv-none-elf-gcc-15.2.0-1 --dtype float32 --output build/t6_fp32_new
python3 -B tools/reproduce_rv32_samples.py --toolchain build/t4_toolchain/install/xpack-riscv-none-elf-gcc-15.2.0-1 --dtype int32 --output build/t6_int32_new
python3 -B tools/reproduce.py --output build/t6_pc_new --iterations 200
```

副本不携带旧build/ELF/仿真器；固定工具链为显式外部依赖并完整校验。本轮沿用T4 portable-metadata本地兼容RTL，原上游不改；不是原始RTL在所有仿真器的普遍结论。

## 过程及边界

初轮边界通过，新增异常固件遗漏必需recover回调导致bind失败，已补齐；build/t6_pre_review保留。修复后build/t6_pre_review_v2的27原FP32全部通过，blocked/failed/unproven/tool_error均0；最终当前源码验收如下，不以初验替代。

一次独立只读审查0 Critical/1 Important/1 Minor：缺失证据被误标确认失败、双侧无输出被误标逐位相同。后一项按用户未知状态要求重评Important，一轮修复；两个入口级测试四个反例先FAIL，修复后8/8专项通过，真实数值/重复/单双不一致仍失败。缺摘要或host异常保持unproven；没有两侧完整有效输出时single_dual_bitwise_equal=null。无延期，不二次独立复审；最终全回归由实施者完成。

尚未验证实板、FP32多节点目标整链、真实模型/量化/质量、真实时间/profile、完整最坏栈/ISR、DMA/DDR/cache/OS资源、综合时序、形式等价、完整IEEE754和其他工具/仿真器版本。已测sp仅有限路径观察，未测项保持未知；静态调用方区域不构成目标动态分配器释放证明。

## 最终实际结果

三份源码副本各317个源/数据文件，初始不含build，运行前后源与副本指纹一致。PC入口build/t6_pc_final/report.json，INT32入口build/t6_int32_final/report.json，FP32入口build/t6_fp32_final/report.json；每例ELF/map/属性/反汇编/.su、物理输入/导出、PC原始输出及UART日志在各目标副本workspace/build/samples/。两条真实仿真器均重新构建，固定工具链是显式校验的外部依赖。

| 范围 | 实际结果 |
|---|---|
| 原冻结清单 | 54例/109文件不变；本轮FP32 27例（24 linear、2 add、1 relu），原shape/storage/dtype/layout及物理输入/权重SHA均保留 |
| FP32参考 | 正常/零输入与Python标量、独立NumPy、PC直接C、PC独立静态C比较；正常目标输出另直接比较冻结expected；沿用atol=1e-6/rtol=1e-5，逻辑有限、padding为+0字节 |
| FP32目标 | 27/27，单/双54个配置执行、270份有效输出；1296个逐参考比较最大绝对误差0、逻辑逐位一致；同ELF两配置、同输入重复/恢复/rebind输出逐字节一致 |
| 重复/异常 | 每配置5次有效输出、另1次同步未知并保护输出/关闭/恢复；13组契约/生命周期检查。额外半偶/最小次正规/相消/接近上限边界，两配置严格手算bit pattern通过；NaN/±Inf输入拒绝、core非有限再检查、第二元素溢出时全部输出原子性、重新供零恢复均通过 |
| TCM | 原27 FP32 blocked_tcm=0，无缩形/截断/替换；额外65536字节真实静态区链接负控正确拒绝；failed/unproven/tool_error均0 |
| FP32布局/栈 | 初始化镜像30808—31544字节；最高BSS末32736低于栈底57344；两配置样本观察栈均1120字节，无trap/栈越界/未对齐 |
| INT32回归 | 新共享入口27/27，两配置/重复/异常/原溢出与容量负控通过；27份ELF与T5相同指纹，观察栈816。不是把旧报告算作重跑 |
| PC完整回归 | 原174/174＋工具58/58，无跳过/失败/错误；54样本、两类型四节点链×原/零、24压力/200轮、6原生含3sanitizer通过 |
| 实板/真实模型 | 未验证，deployment_ready=false；其余未知保持前述边界 |

1120字节属于T6 FP32样本固件的有限路径观测，816属于同轮INT32；T4的752属于另一固件。都不是完整最坏调用链/ISR栈。64KiB TCM/8KiB预留栈不是板端OS或真实模型可用预算；32位范围探针是数学地址跨度核对，不是对0xffffffff真实访存。

实际选用rv32im/ilp32/libgcc.a，SHA256为75dbc04c0e750a7e12ff7c690f0f1750cb87c68e87e0b0c9748b2754ea92b680。它及其受控安装内容经过固定压缩包校验，不能由“库存在”推断完整软浮点语义：本轮以真实边界及27例执行支持有限结论。

封存入口build/t6_finalize.py重新核对所有新报告/产物SHA、逐例原映射/PC物理输出/54份FP32与54份INT32 UART门禁、额外故障及容量探针、原174测试/109输入、核心/静态运行时/T5固件/启动链接/驱动/RTL选择源，以及S1—S6/T1—T4/T4D/T4C/T5旧13份收据及全部旧证据。只本报告、计划、progress在运行后完成收尾，受测副本与最终指纹分列，不覆盖旧基线。原地保留，未提交/推送。
