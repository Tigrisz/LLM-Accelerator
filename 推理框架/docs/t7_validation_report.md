# T7：原FP32/INT32四节点静态链RV32迁移

2026-10-28，最终当前源码PC及双链干净副本验收通过，原FP32链迁移与INT32链回归完成；TCM阻断0。运行时0.6.0/nativeABI2/coreABI1/wirev1保持，不绑定模型/W4A8。汇总build/t7_validation_final/report.json，完整性build/t7_final_integrity.json，指纹build/t7_baseline.json/.sha256。

直接复用inference_ref/package_validation.py的chain_definition：9张量、4节点linear→relu→add→linear。x[3]、w[2,3]、bias/delta[2]、w2[2,2]及4个[2]激活保持；原输入[2,-3,4]、常量、布局及storage_shape保真。原输出手算[20,-25]，零输入[0,-5]。核对T6原源码指纹后固定两类型规范定义SHA，并在导出前核对真实包/权重/输入；执行入口无需历史build。

PC以Python标量、NumPy、直接C逐节点及独立纯C静态整链对照手算结果。FP32仍存储FP32/计算FP64展开累加/末端舍入，容差atol=1e-6、rtol=1e-5；逐位一致单列。每类型一份正向ELF供单/双配置，每配置原→零→原、同步未知恢复后原、close/rebind后原五输出，均要求完成4节点并对照参考；同输入和单/双字节确定性另验。沿用13组契约检查，无golden嵌入正向固件。

新增独立故障固件：原完整链和权重复制，绑定后仅故障注入修改delta首元素（FP32 NaN/INT32 INT_MAX），第三节点拒绝，完成2节点、最终输出不可见；恢复注入数据并重新供原输入后完成4节点并输出原结果，再供零输入完成4节点并关闭。没有调用irs_recover冒充数值错误恢复：此时已知静止，可修复重跑；同步未知恢复由正向固件另行验证。已有节点按节点提交且arena可复用，**不承诺整链物理内存回滚**，不检查最终槽位保持某哨兵。

复用T6实际软浮点库检查及舍入/次正规/NaN/±Inf/溢出探针，复用额外INT32溢出和65536字节真实超容量链接负控。链包不缩形、不分片；正向和故障镜像分别按真实map/ELF分类容量。blocked_tcm不计数值通过，tool_error/failed/unproven分列；两种dtype必须齐备。54冻结样本本轮只核对完整性并做PC回归，不冒充54样本目标重跑。

目标沿用固定xPack15.2.0-1、rv32im_zicsr_zifencei/ilp32/小端soft ABI、无F/D/A/C/V；工具链安装每次对照固定压缩包完整检查。RTL为T4 portable-metadata本地兼容层，上游不改，非原始RTL跨仿真器或实板证明。64KiB TCM/8KiB预留栈是测试布局，非真实OS/模型预算。

## 复现

Linux/WSL，输出目录必须不存在：

```sh
python3 -B tools/reproduce_rv32_samples.py --toolchain build/t4_toolchain/install/xpack-riscv-none-elf-gcc-15.2.0-1 --workload chains --output build/t7_chains_new
python3 -B tools/reproduce.py --output build/t7_pc_new --iterations 200
```

chains显式跑原两dtype，--dtype仅影响samples。父入口从源码生成干净副本，不携带旧build、ELF或仿真器，工具链是显式校验的外部依赖。默认samples入口保留，工具报告v3新增workload/链清单，不改native ABI或磁盘格式。

## 初验及边界

build/t7_pre_review/report.json实际2链通过、容量阻断0，4个正向配置/20有效输出、4个中途故障配置/8恢复输出；原/零结果与参考一致。两正向镜像各31744字节、BSS末34208；观察栈INT32 816、FP32 1120，故障固件分别656/1040。源副本321文件，无旧build，前后不变。工具初验61/61，3项新门禁先FAIL后通过。

一次独立只读审查0 Critical/Important/Minor。独立运行3项T7测试、重解析正向/故障两类型两配置日志、匹配ELF身份，并核对734份初验产物SHA，均通过；T6保护源码未变。无延期，不二次复审。审查重放不替代下述由实施者执行的最终当前源码回归或历史证据核验。

仍未知：实板、其他工具/仿真器/原始RTL、真实模型与量化质量、任意更大链/动态形状、完整IEEE754/动态舍入、最坏调用链/ISR栈、真实性能、综合时序/形式等价、DMA/DDR/cache/OS资源及动态分配器释放。有限sp观测不能升级为最坏栈；第三节点错误覆盖不是任意节点/任意故障保证。

## 最终实际结果

build/t7_pc_final/report.json与build/t7_target_final/report.json均passed；两副本各322个源/数据文件，初始无build，运行前后源/副本指纹一致。目标原始产物在后者workspace/build/samples/，包括两个新仿真器、各链及故障独立ELF/map/属性/反汇编/.su、PC原/零输入/输出及真实UART stdout/stderr。

| 验证范围 | 实际结果 |
|---|---|
| 原链保真 | 两dtype原9张量/4节点、shape/storage/常量/输入和布局均锁定，原链源码与T6一致，导出包回读和物理权重/输入核对 |
| 正向数值 | FP32与INT32各自同ELF单/双运行；原输入[20,-25]、零输入[0,-5]，Python标量/NumPy/直接C/独立静态C/手算最大绝对误差0；FP32目标比较逐位也一致 |
| 重复/生命周期 | 4个正向配置、20有效输出；每配置原/零/原、同步未知恢复后原、关闭重绑后原，13组契约检查，另4次同步失败的未知状态及输出/关闭/恢复保护通过 |
| 中途异常 | 4个故障配置：FP32第三节点status5、INT32 status6，完成2、输出不可见；恢复delta/重新供原及零输入后均完成4，8份恢复输出正确，关闭成功。不是整链物理回滚或irs_recover数值错误接口 |
| 容量 | 两原链及故障镜像均装入测试TCM，blocked_tcm=0，未缩形/分片；真实65536字节额外静态段负控正确拒绝；failed/unproven/tool_error均0 |
| 布局/栈 | 两正向镜像各31744字节、BSS末34208；故障各29952字节、BSS末31584，均低于栈底57344。正向观察栈INT32 816/FP32 1120，故障656/1040；无trap/栈越界/未对齐 |
| 软浮点/额外负控 | rv32im/ilp32 libgcc实际身份/宏/ISA/符号/反汇编检查、T6舍入/次正规/非有限/溢出/原子性/恢复及原INT32溢出探针通过；不推断完整IEEE754 |
| PC回归 | 原174/174＋工具61/61，无跳过/失败/错误；54样本、两dtype四节点链×原/零、24压力/200轮、6原生含3sanitizer通过 |
| 实板/模型 | 未验证，deployment_ready=false；未知边界保持上文说明 |

64KiB TCM/8KiB栈保留为测试布局；观察栈不是完整最坏调用链/ISR，32位跨度检查不是对高地址真实访存。两条受测静态链不代表任意FP32图或真实模型可部署。本轮54单节点样本仅PC回归，T5/T6目标证据保持历史状态，未重新计数。

build/t7_finalize.py封存前重新核验两个最终报告/源码副本及所有产物SHA、实际正向/故障日志门禁、原包/物理输入权重/ELF及PC输出、额外探针、原174测试/109输入、核心/静态运行时/原链定义/T5T6固件/启动链接/驱动/RTL和FP比较器未变，以及S1—S6/T1—T4/T4D/T4C/T5/T6旧14份收据及全部旧证据。只本报告、计划和progress运行后完成文字收尾，受测与最终指纹分列。原地保留，不提交或推送。
