# T4：RV32 最小静态链的交叉构建与 RTL 仿真

当前入口默认`--rtl-mode portable-metadata`选择本地组合wire兼容改写，必须同时验证单/双发射。初次T4使用原始RTL/Verilator5.032出现的双发射失败属于历史结果；独立Icarus原RTL执行同一ELF通过，后续T4D已定位当前Verilator生成模型的元数据更新排序问题。`--rtl-mode upstream`保留原始对照。最新字段/收尾见[收尾记录](t4_closeout_report.md)，定位证据见[T4D历史记录](t4_dual_debug_report.md)，旧build报告不修改。

T4使用模型无关的四节点INT32合成链，保持运行时0.6.0、native ABI2、core ABI1及IRS4BIN1/v1。PC离线解析/规划/导出，RV32固件嵌入执行描述和权重、绑定caller-owned元数据/arena、执行并读取输出。固件运行不调用Python，不使用堆；此入口没有模型、量化或W4A8假设。

当前默认验证范围是兼容副本的**单发射和双发射配置**，同一ELF直接用于两配置。upstream模式仍只以单发射为通过范围，另记录原双发射诊断。仿真通过不能证明VibeOS或实板接入完成；状态分别见`rtl_selection`、`rtl_profiles`、`verification_target`、`default_configuration_verified`、`all_profiles_passed`、`deployment_ready`、`board_verified`。

## 工具与来源

- [xPack官方发布15.2.0-1](https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/tag/v15.2.0-1)，GCC15.2.0；Linux x86_64包433494794字节，SHA256 `aaaa8060c914851a3e5ee1ba82cc3d6f80972f90638a05c6e823a37557a33758`。
- 固定在`tools/target_toolchain.lock.json`；本地解压，不全局安装或修改PATH。准备收据记录完整版本、宏、multilib、实际选中libgcc/libc/libm及SHA256。当前选中`rv32im/ilp32`。
- 准备及每次执行均以SHA固定的官方压缩包重新派生完整内容指纹，比较安装内全部文件/链接（含cc1/collect2/binutils/头文件/specs），拒绝额外文件。该校验会读取整个发布包和安装内容，耗时高于只检查驱动；无需信任可编辑收据中的自报文件哈希。早期准备收据可继续使用，但必须经当前完整复核后才允许执行。
- [主仓库固定提交](https://github.com/Bytestring0/FPGA_RV32IM_VibeOS/tree/c1bc715b276db48cf6e6b640701d51b72e984d77)；使用T2已归档`docs/target_platform_sources/main/fpga/generated/qinglong_all.sv`及manifest哈希。未修改上游RTL。
- Verilator5.032编译真实`qinglong_soc`，没有用宿主计算或通用ISA模拟器替代CPU执行。当前主验收分别显式构建`DUAL_ISSUE=0/1`，其他参数相同；参数表同时生成实际-G参数和报告，拒绝缺项/重复/隐藏覆盖。T4D两仿真器共80次交叉矩阵（其中Icarus40次）属于历史执行，当前收尾核对其证据，是否重新执行以收尾报告为准。

## 复现入口

Windows经WSL运行。要求Linux x86_64、Python>=3.12（安全tar解压filter）、NumPy>=1.24、Verilator、make及宿主C++编译器；PC全回归另需gcc/cc。构建目录必须不存在，不覆盖旧结果。

在本目录的WSL shell中，一次性下载和准备（实际下载地址/校验来自lock，不使用系统同名交叉编译器）：

```sh
mkdir -p build/t4_toolchain
curl -fL --retry 3 -o build/t4_toolchain/xpack-riscv-none-elf-gcc-15.2.0-1-linux-x64.tar.gz https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/download/v15.2.0-1/xpack-riscv-none-elf-gcc-15.2.0-1-linux-x64.tar.gz
python3 -B tools/prepare_rv32_toolchain.py --archive build/t4_toolchain/xpack-riscv-none-elf-gcc-15.2.0-1-linux-x64.tar.gz --output build/t4_toolchain/install
```

已有当前受测安装时直接指定它；完整源码副本重建/仿真：

```sh
python3 -B tools/reproduce_rv32.py --toolchain build/t4_toolchain/install/xpack-riscv-none-elf-gcc-15.2.0-1 --output build/t4_target_new
python3 -B tools/reproduce.py --output build/t4_pc_new --iterations 200
```

PowerShell调用方式：`wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec python3 -B tools/reproduce_rv32.py --toolchain build/t4_toolchain/install/xpack-riscv-none-elf-gcc-15.2.0-1 --output build/t4_target_new`。

`reproduce_rv32.py`只拷贝源码、冻结样本及归档RTL，无旧build、ELF、共享库或Verilator产物；工具链作为显式外部依赖，重新核对准备收据及官方压缩包对应的完整安装内容。原始压缩包须保留；旧准备收据默认在安装目录的上一级查找lock所指定包名，新收据明确记录路径。它不自动联网下载，也不将本地工具缓存称为零外部依赖。`tools/run_rv32.py`为单工作区实际构建入口。当前工具报告v2：默认portable-metadata模式退出0须通过`single_and_dual_issue`；upstream模式退出0只表示`minimal_single_issue`。报告保留`rtl_selection`原始/所选SHA、local_overlay及upstream_modified=false；任何模式都不能据仿真退出0宣称实板部署。

## 单、双发射参数汇总契约

报告v2新增`rtl_profiles_version=1`、`rtl_profiles.single_issue/dual_issue`，干净副本父报告同步相同字段。每项包含`parameters`、真实`build_command`、`normal_elf_sha256`、`rtl_sha256`、正向result/validation、`simulation_passed`和负控tested/result/validation；失败为false、未证实为null、未执行负控tested=false且result/validation=null，不互相替代。board_verified=false、full_stack_worst_case=null保持。

默认模式在双发射正向未通过时，先形成已有single/dual记录，再停止后续双发射负控。子`failure.json`保留`target_result=false/null`、classification和rtl_profiles，父`failure.json`透传同一分类，不以FileNotFoundError覆盖。入口/编译工具在形成目标证据前失败仍保持null。这一失败路径由受控注入入口探针覆盖，不冒充新CPU异常执行。

| 参数 | single_issue | dual_issue |
|---|---|---|
| DUAL_ISSUE | 0 | 1 |
| RAM_WORDS | 16384 | 16384 |
| SIM_FAST_UART | 1 | 1 |
| CLOCK_HZ | 27000000 | 27000000 |
| PREDICT_ENABLE | 1 | 1 |
| BTB_BITS | 8 | 8 |
| LOAD_BYPASS | 1 | 1 |
| EARLY_LSU | 1 | 1 |
| INIT_FILE | firmware.hex | firmware.hex |

`tools/rv32_profiles.py`为当前受测配置的唯一参数来源，两条构建命令均显式传入全部9项。数据是测试配置身份，不是板端可用预算或目标时钟实测。legacy `verified_rtl_parameters`保留原来的8项单发射字典，`verified_rtl_parameters_scope`明确其为弃用的single_issue摘要；它不是双配置推荐入口。runtime/native/wire/API版本不因新增报告字段改变。

## 接口、布局与证据

`c/rv32/start.S`建立gp、16字节对齐sp、mtvec并清BSS；trap/正常终止均写主仓库done MMIO。`firmware.c`直接调用现有`irs_read_info/inspect_v2/bind_v2/input/run/output/close`及原C数值核心。嵌入blob代表本次读取来源，不代表SD/DDR/VibeOS文件接口已接通。

交叉参数`-march=rv32im_zicsr_zifencei -mabi=ilp32 -Os`。门禁同时检查编译宏、ELF32小端/RISC-V/flags=0、实际链接ISA属性及16字节栈对齐；拒绝LP64及C/A/F/D/V扩展。map/readelf/nm/objdump、全部本轮编译单元`.su`、工具命令和stderr均保留。链接无未解析符号，无malloc/calloc/realloc/free/_sbrk。Newlib/libgcc来自已校验发布包；实际`fegetround`为无FCSR访问的软件实现，不能据此声称FP32计算已在目标验证。

`link.ld`是本测试固件布局：64KiB TCM地址0，栈区`[0xE000,0x10000)`共8192字节；BSS须在栈下。这是链接预留，**不是实板可分配预算或已证明足够的栈额度**。text/rodata ELF段RX、data/BSS段RW仅描述文件属性，TCM无新增内存保护。目标平台/OS最终可用内存图仍待确认。

RTL驱动观察两条retire通道的sp写回，启动sp=0x10000后检查范围及16字节对齐，统计最小sp。观察高水位只对本次有限输入及执行路径成立；未覆盖ISR嵌套、所有错误路径、未来算子/模型、库全部调用路径或实板。`.su`是逐函数编译栈帧，不能相加成已证明的全程序峰值；预编译库缺少对应`.su`。`full_stack_worst_case=null`保持。

TCM同步回调执行真实`fence iorw,iorw`并计数；CPU顺序执行完即静止，恢复不代表异步设备。`clock()`明确返回不可用，profile及now_ns为空；时间/profile可用标志均为0。没有伪造目标时间、异步DMA、缓存维护、DDR、设备驱动或完整目标追踪。

## 验收边界

正常输入`[2,-3,4]`输出`[20,-25]`，零输入输出`[0,-5]`，分别由独立Python标量/NumPy参考计算；PC原有双类型链回归提供C对齐。本次RV32只执行INT32链，54样本和FP32链仍属于PC结果。

固件同时拒绝短执行描述、检查区不足、state容量不足；绑定后覆盖临时检查区再执行，证明它不被持久借用。另构建错误期望值固件，必须完整RTL摘要中实际退出10且无trap/栈违规；10周期watchdog必须收到恰好10周期、done=0、无trap的完整摘要且宿主退出1。宿主崩溃不能替代负控。工具错误/超时/缺失证据判未证实，已观察trap/栈违规即使没有done也判目标失败；分类器不自动推断根因，特定历史故障的归因见T4D证据。

初次T4曾将原始Verilator双发射异常列为待定位；T4D已给出首次差异、生成模型赋值顺序、56字节复现、Icarus反证和兼容改写证据。当前兼容副本的受测仿真已通过，这不证明CPU硬件缺陷或部署就绪。形式等价、其他Verilator版本、硬件下载、PDS综合/时序、实板输出/栈/计时、真实模型均未验证。
