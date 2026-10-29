# T2 目标平台约束清单 v1

T3起本页为**T2历史约束快照（运行时0.5.0）**；9份当时框架源已按原指纹固定在framework_t2/，来源索引相应指向快照。
T2原始build收据/证据不改。本页32KiB/20KiB是T2发现，不代表T3当前占用；当前改动和未知边界见[t3_metadata.md](t3_metadata.md)。

核对日期2026-10-25，运行时仍0.5.0，现有ABI/API和磁盘格式不变。
[机器清单](target_platform_constraints.json)共54项，覆盖工具链、ABI、端序、浮点、内存、栈、读取、计时、同步9领域；逐项含值、状态、范围、影响、来源行号，未知另有解除条件。
本清单是接入依据，不是allocator/链接器的可直接使用配置，`target_ready=false`。

## 来源与状态

主仓库固定到[`c1bc715b276db48cf6e6b640701d51b72e984d77`](https://github.com/Bytestring0/FPGA_RV32IM_VibeOS/tree/c1bc715b276db48cf6e6b640701d51b72e984d77)。
27份相关文件快照在[target_platform_sources/main](target_platform_sources/main)，按Git blob SHA-1与SHA-256核对；不是完整可构建仓库，不执行其中脚本。
[来源清单](target_platform_sources/manifest.json)共43项，另含现有框架C/平台源、PDF选页文本与环境记录。

用户提供的《紫光同创.pdf》PDF10—11/印刷8—9页说明赛题一和编译工具；板卡配套《教程1_硬件实验指导手册_盘古676系列100Pro+开发板.pdf》PDF19/24、21—23、43—44页分别支持器件/DDR、时钟和UART规格。
原PDF绝对路径、整文件SHA256、提取页号在[local_pdfs.json](target_platform_sources/local_pdfs.json)，选页文本随清单保存；指南PDF11与手册PDF24已渲染并目视核对。
物理规格以手册为据，当前CPU映射以RTL/链接脚本为据；文档内未来OS/模型方案不当作用户新指令或已实现功能。

规范来源：[RISC-V psABI](https://riscv-non-isa.github.io/riscv-elf-psabi-doc/)（所读页标注2026-10-14 draft）、[GCC选项](https://gcc.gnu.org/onlinedocs/gcc/RISC-V-Options.html)、[Zifencei 2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/zifencei.html)、[计数器2.0](https://docs.riscv.org/reference/isa/v20260120/unpriv/counters.html)。
版本/章节/简短释义保存在[official_sources.json](target_platform_sources/official_sources.json)，活网页可能变化，释义快照不是规范原件或认证。

| 状态 | 含义 |
| --- | --- |
| source_confirmed（30） | 固定源码/原始资料明确给出，不是本轮硬件执行 |
| normative（2） | 官方规范期望，不是目标编译测量 |
| derived（3） | 根据所引类型/参数计算，不是目标测量 |
| historical_report（3） | 上游归档记录，本轮未重跑 |
| proposed（3） | 设计稿或后续建议，未实现 |
| unknown（13） | 证据不足，值为null，附解除条件 |

## 工具链、ABI、端序与算术

| 核对项 | 结论和接入限制 |
| --- | --- |
| 板型/器件 | MES2L676-100HP / PG2L100H-6IFBG676；手册、board_system及PDS资料一致，本轮未读取物理设备身份 |
| 编译器名称 | 指南写riscv32-unknown-elf-gcc，仓库Makefile默认riscv64-unknown-elf-；名称差异保留，不能由前缀判断位宽；RV32 multilib及赛务名称/版本要求待确认 |
| ISA | 默认rv32im_zicsr_zifencei，CoreMark优化配置另启Zba/Zbb；不预设A/F/D/C/V或完整B。misa仅报告I+M，不用它单独判断全部扩展 |
| ABI/链接 | -mabi=ilp32、freestanding、nostdlib/nostartfiles、-lgcc；不默认newlib/libm/POSIX可用 |
| 规范类型 | int/long/pointer/size_t为4字节，long long/double为8，long double为16；标准入口sp对齐16字节；这些是ILP32规范期望，目标sizeof/offsetof尚未测 |
| 端序 | CSR与LSU字节通道确认小端；IRS4BIN1仍是显式小端无指针格式，typed权重和本机元数据仍须正确对齐 |
| 非对齐 | 当前半字/字非对齐访存陷阱，不自动拆分；不能直接把压紧字节流强转原生结构 |
| FPU | 当前整数译码/寄存器系统无FPU；soft-float ABI不等于软件算术库就绪，禁止生成F/D/Zfinx指令 |
| 当前参考路径 | FP32存储、binary64扩展累加，fegetround要求FE_TONEAREST；禁止fast-math和FMA合并。目标需验证软件库舍入/非有限/抵消/溢出与代码体积 |
| 可选profile | C核心使用clock/CLOCKS_PER_SEC及long double比较；不传profiles也不能凭猜测消除整个翻译单元的链接依赖；int32入口同理 |
| 当前工具探测 | 当前Windows/默认WSL PATH无具名交叉GCC；默认WSL具名dpkg包不存在；有限/opt、/usr/local搜索未找到。不声称全磁盘/全部发行版都没有工具 |
| 历史环境 | 81MHz UART归档写GCC13.2.0；PDS工程写2022.2-SP6.1 build138931，均非本轮工具或构建结果 |

WSL Ubuntu26.04.1中readelf2.46、Verilator5.032可见，但它们不等于目标编译器，未据此运行RTL回归。本机不存在仓库文档中的D:\FPGA\RiscV路径，使用GitHub固定提交快照。
目标库、实际ELF、RV32结构布局、soft-float支持/成本仍未知；不能复制PC ctypes布局或用PC GCC版本填空。

## 当前内存图与栈

依据：[qinglong_soc.sv](target_platform_sources/main/rtl/qinglong_soc.sv)、[link.ld](target_platform_sources/main/sw/link.ld)、[start.S](target_platform_sources/main/sw/start.S)。

| 区域/地址 | 当前实现与限制 |
| --- | --- |
| [0x00000000,0x00010000) | 16384×32bit=64KiB统一双端口TCM，板顶未覆盖容量；代码/常量/data/BSS/栈共享。双端口及综合复制BRAM不增加软件容量 |
| [0x0000E000,0x00010000) | 链接ASSERT要求__bss_end严格小于0xE000；这是最小8KiB栈保留，没有独立guard/运行高水位证明 |
| 0x10000000 | UART TX，读bit0 ready，写低字节，硬件背压；无RX |
| 0x10000004 / 08 | 32位退出码/done、GPIO；不是普通RAM或通用系统调用 |
| 0x10000100 / 104 | mtime低/高32位，CPU clk递增、复位清零 |
| 0x10000108 / 10C | mtimecmp低/高32位；后续分半写序列须防误中断 |
| 0x10000110 | msip bit0 |
| 其余未译码地址 | 总线错误；32位可表示不代表可访问 |
| 物理DDR3 | 手册：两颗4Gbit（每颗512MB），总8Gbit=1GiB、总线32bit；当前SoC无DDR控制器/校准/译码，不能作arena |
| [0x80000000,0xC0000000) | OS设计稿建议DDR窗口，尚未实现；其64MiB系统预留也只是建议 |

`__bss_end < 57344`是代码/静态数据末端限制，**不是56KiB剩余推理容量**。无本次推理固件map，实际空闲未知；链接脚本也未定义heap/heap_end/_sbrk，不能假定malloc可用。
目标arena、heap、trace、task、C元数据和栈峰值预算全部为null。PC DEFAULT_BUDGET=64MiB和PCAllocator额度不迁入目标配置。
TCM起始地址0用于复位代码；当前C拒绝非空NULL缓冲，不能把地址0当非空arena传入。uint64文件偏移、RV32 size_t和真实译码范围分别校验，对齐/区间/生命周期也必须通过。

当前`irs_context`的roles[4096]和supplied[4096]两数组按类型共20480字节，尚未加其他字段，不是完整目标sizeof。
`irs_inspect`的first[4096]、last[4096]按ILP32 int=4共32768字节固定局部数组，尚未加调用者、函数框架、算术临时对象和ISR。
这已超过8KiB最小栈保留，是T3的直接阻碍。8KiB不是测得最大可用栈，不能据此宣布所有小链都不可能装入TCM；也不能凭PC transient检查通过宣布目标栈安全。
应先收缩/移出工作集、明确metadata上限和存放区，再以目标sizeof、-fstack-usage、map、调用图及栈canary验收；default_trap目前只报告并停机，不是完整ISR或独立推理任务栈。

## 平台接口映射

| 现有契约 | 目标侧现状/后续验收 |
| --- | --- |
| Reader.size/read_at(uint64 offset,size_t length,&actual)、read_exact | 当前只有firmware.hex初始化TCM，无模型/SD/UART RX通路。irs_reader还在含stdio的ir_pc.h；须提炼无FILE依赖接口、选择来源，覆盖大小快照、短读、越界、32位长度、错误释放 |
| 调用方提供arena/context/tensors/calls，irs_run无malloc | 尚无目标分区/allocator。PC加载器calloc/FILE/stat不可直接作为裸机实现；小型合成blob内嵌是后续建议，不是已实现入口 |
| now_ns有效才返回1，否则0 | read_cycles已有高/低/高重读；cycle可抑制/重写，mtime复位清零；目标镜像频率未知。raw ticks不能充当ns，不可用时返回0 |
| 追踪/节点profile | 现有trace字段仍叫host_ns，节点用clock ticks；目标接入前必须明确域/单位/频率，必要时版本化，不能把设备周期暗标主机时间 |
| sync(direction=1发布/2获取)，0确认，非0未知 | RTL存在FENCE序列化/FENCE.I取指与预测清理，但未实现C目标回调；纯CPU/TCM路径也要证明编译器和硬件顺序 |
| recover=0确认静止，未知保留arena | 当前只有PC实现；目标需真实停止/恢复确认，不能超时就释放或输出有效结果 |
| backend query/execute/completed/quiescent | 接口可复用，但主仓库无AI/DMA集成；独立加速器工程UART切片不能当CPU驱动。未来设备需寄存器、地址/对齐/长度、完成、错误、abort/reset和在途总线确认 |

当前自定义valid/ready总线每接口最多一个未完成事务，不是AXI；板顶irq_external绑0，没有加速器完成IRQ。无A扩展，不默认AMO/LRSC锁库可用；MIE临界区仍是OS设计提议。
FENCE的访存顺序、FENCE.I的本hart取指可见性、数据cache维护和DMA完成分别核对。编译器memory clobber也不是硬件FENCE。未来若加cache/DMA必须补充真实维护和静止证明。

时间源不能随意选择默认值：FPGA顶层/board_system是27MHz，独立SoC默认50MHz，独立PLL模块默认108MHz。
归档81MHz是上游报告的闭合实板配置，108MHz是负WNS实验；本轮未重跑，晶振也未外部校准，不能从CoreMark推算推理吞吐。
建议未来用商余数换算ticks→ns，检查hz>0、每次乘法溢出、暂停/复位、单调性和域；该转换未接入，换算精度不等于实际分辨率。

## 13项未知与下一步验收

未知项：当前交叉工具链、目标库、原生结构布局、soft-float语义/成本、profile时间/长双精度依赖、实际空闲内存、heap预算、arena预算、trace/task/metadata预算、运行栈峰值、读取适配器、实际镜像时钟、同步恢复回调。逐项解除条件见JSON的unblock。

1. 工具包/ABI：记录路径、版本、哈希、dumpmachine和multilib；编译默认ISA/ilp32探针，readelf检查ELF32/RISC-V/小端/soft-float ABI/属性/无RVC，核对外部符号和目标sizeof。
2. T3工作集适配：解决32KiB局部数组，明确tensor/node上限和context位置，兼容性变化单列；map+.su+调用图覆盖正常/异常/ISR，静态池/栈/镜像不重叠，超预算拒绝。
3. 最小平台适配：分离reader与FILE依赖，选小型合成blob、静态arena，补时间域和纯CPU同步/恢复；实际验证短读/越界/分配失败、时间不可用、未知隔离及释放。
4. 分级执行：交叉编译→RTL仿真→实板小型整数链，浮点等目标库确认后单列；各级结果分开，不把PC通过当RV32通过。54样本/双链继续作PC基线，不要求全部fixture同时常驻64KiB。

T2不绑定具体模型、W4A8或硬件分组，不替团队选择DDR/OS/模型配置，不新增算子或板端执行能力。

## 离线核对入口

框架根目录，Python3.10+，无需NumPy、网络、交叉GCC或历史build：

```text
python3 -B tools/check_target_platform.py --output build/t2_audit_new.json
```

可加`--probe-environment`只读探测当前PATH/具名包，仍不编译、不上板、不自动补清单。输出文件必须不存在。
检查固定43来源身份/路径及SHA256、27份必需Git blob/ref/URL，交叉核对仓库/提交和repository索引；另查54身份/9领域/13未知、关键容量推导、来源定位、null预算与不绑定模型/量化。
这是快照完整性及明确不变量门禁，不是自然语言语义证明、架构认证或硬件ready证明；来源/范围改变需人工复核。结果见[T2验证记录](t2_validation_report.md)。
