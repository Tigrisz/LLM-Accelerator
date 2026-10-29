# T8 当前版本统一总验收

2026-10-28。运行时0.6.0/native ABI2、ir_core ABI1、IRS4BIN1 v1保持；本阶段只增加验收编排、证据重放和严格状态分类，不绑定模型或量化。

## 使用

在WSL Ubuntu和框架根目录运行，output必须不存在：

```text
python3 -B tools/reproduce_total.py --toolchain build/t4_toolchain/install/xpack-riscv-none-elf-gcc-15.2.0-1 --output build/t8_new --iterations 200
```

显式工具链及压缩包为外部依赖，逐项核对固定归档/安装指纹。其余源码快照不携带历史build；同一新副本先从空build构建并执行PC全量，再重新构建RV32公共对象与单、双发射仿真器，运行全部54样本和两条四节点链。每个固件在两种配置间使用同一ELF；不会使用历史ELF/报告。旧samples/chains入口保留，all目标报告v4，父入口及总报告v1。

## 覆盖和门禁

56项逐项保留原shape/storage_shape、布局、输入和权重；冻结109文件与suite SHA固定。样本27 INT32/27 FP32，原两链各9张量/4节点，链定义指纹和原输入均核对。参考包括Python标量、NumPy、PC直接C与静态C；受测RV32运行本身不依赖Python。

每项正常固件覆盖原输入、零输入、重复原输入、同步未知恢复、close/rebind恢复，5份有效输出；两条链另有第三节点错误、完成2节点、最终输出不可见、修复后正常/零输入各完成4节点。不提供整图回滚。

软浮点边界、非有限/溢出及修复、INT32溢出和真实65536字节BSS容量负控同批执行。主56项与额外探针分列；容量负控预期链接拒绝不等于样本容量阻断。使用一份真实成功FP32日志在主机上构造错误参考、缺少摘要、宿主异常退出、重复输出四个门禁反例；这些是主机判定器测试，不冒充额外RV32执行。

重放程序重新读取实际输出文件、UART、ELF、ABI/布局和构建参数；计数来自实际阶段记录。缺项、重复、缺配置、不同ELF、输出缺失均不能通过。状态为passed/blocked_tcm/failed/unproven/tool_error：明确数值/陷阱错误为false，容量/证据不足/工具错误为null；CLI仅全部通过返回0。流程结束与全部RV32数值验证分别记录。容量只凭实际链接容量诊断，不缩形。

## 当前执行记录

首份build/t8_pre_review在PC阶段通过后执行会话中断，RV32只产生部分证据，无总报告，不能作为完整验收。原始目录保留。新增6项门禁先RED后GREEN；自查补充整数/链错误分类和实际计数3项先RED后GREEN，专项9/9通过。最终新副本结果见下。

一次独立只读审查提出5项Important，均按证据完整性影响处理：重建原五输出期望及固定边界值；重读PC stdout/stderr/trace和额外探针同ELF；链名绑定dtype/原拓扑/常量/输入/包指纹及固定容差；完整数值/跨配置字节错误保留failed；all目标报告容量阻断为null且非零退出。7个新增回归先RED后GREEN，专项16/16。未独立复审，最终全量用于修复后验证。预审t8_review_run PC174+70与资源验收通过后为修复主动停止RV32，tool_error/null，不能作为总通过。

build/t8_final中PC174+77、目标56/56通过，但边界重放TensorSpec漏storage_shape，父/子总报告正确为tool_error/null，exit1。保留此失败结果。新增回归直接复现TypeError后显式指定原(6,)物理形状修复，专项17/17；已有原始日志诊断重放通过只证明修复定位，最终验收使用全新build/t8_final_verified，不沿用这些ELF/报告。

## 最终实际结果

build/t8_final_verified/report.json：status=passed、passed=true、child_exit_code=0；同一干净副本328源码/数据文件，初始无build，运行前后原源/副本指纹一致，4070份产物指纹。当前代码、冻结样本和受测副本一致；仅本报告、t8_plan及progress在运行后完成文字收尾，最终指纹另外封存。

| 范围 | 实际结果 |
|---|---|
| PC完整回归 | 原174/174、工具78/78，无跳过/错误/失败；54样本、两类型四节点链×原/零共4记录、24资源探针各200轮、6原生含3 sanitizer通过 |
| RV32主清单 | 原27 INT32+27 FP32样本、原两条9张量/4节点链，共56/56；每例原shape/storage/布局/输入/权重保留，不缩形/截断/分片 |
| 数值/发射配置 | 每例同ELF单、双发射，112个正向配置，560份有效输出；Python标量/NumPy/PC直接C/静态C对照通过。INT32精确；FP32沿用原atol=1e-6、rtol=1e-5，padding规范和重复/单、双发射字节一致 |
| 生命周期 | 每配置原/零/原、恢复/重绑5输出；13组契约，另112次同步未知及可见性/关闭/恢复保护通过 |
| 中途链故障 | 4个故障配置：FP32第三节点status5、INT32 status6，完成2、最终输出不可见；修复后原/零各完成4，共8输出正确；不是整链回滚 |
| 额外探针 | 软浮点边界、非有限/溢出/原子性/修复、INT32溢出共6额外配置通过，逐个实际ELF/同ELF双配置/ABI/输出核验；不混入主56项 |
| 容量/布局 | 主56项blocked_tcm=0；failed/unproven/tool_error均0。65536字节BSS真实链接负控预期拒绝。主镜像最大31744字节、BSS末最大34208，低于测试栈底57344；不代表OS/模型资源预算 |
| 栈 | 主路径观测最大1120字节，仅这些有限路径；完整最坏栈/ISR仍null |
| 主机门禁反例 | 总入口4类真实日志变体通过；另5项只读虚拟产物探针拒绝伪造五输出期望、隐藏PC trace、隐藏额外ELF、链类型替换，并把容差内跨发射字节差异保留为failed/false。均不作为额外目标执行 |
| 实板 | 未执行，board.status=unproven、passed=null、board_verified/deployment_ready=false |

此次共61个固件ELF（56正向、2链故障、3额外探针），122次实际仿真进程；容量链接拒绝和主机反例单列。未独立复审；一次审查的5项Important通过针对性RED→GREEN、完整新副本及实际产物反例验证。

复现父收据：build/t8_final_verified/report.json/.sha256；完整56项矩阵：其workspace/build/total/report.json；逐例原始UART/PC输入输出/trace/ELF/map/.su/参数：workspace/build/rv32_total/。汇总和最终基线位置为build/t8_validation_final/report.json、build/t8_final_integrity.json、build/t8_baseline.json/.sha256；封存脚本build/t8_finalize.py逐项核验源码/受测副本/产物及旧收据。失败、中断和主动停止的运行保持原状态。

封存前旧15阶段收据及20229次历史证据哈希核验通过；原174测试源、109冻结输入与C运行时/固件/链定义不变。当前源码219份+冻结109份；受测与最终指纹分开，不覆盖历史基线。未提交或推送。

## 验证边界

PC全量、所选RTL仿真、实板三层分开。RV32沿用固定xPack GCC15.2.0-1、rv32im_zicsr_zifencei/ilp32/little/soft ABI与本地portable-metadata兼容RTL；未证明原始RTL在其他工具的全量等价、形式等价或综合时序。64KiB TCM和8KiB栈预留是本测试链接布局，不能替代OS/模型可用资源。栈低水位仅受测有限路径，完整最坏栈/ISR峰值未知。实板、DMA/cache/DDR、硬件加速器、真实模型精度/性能、完整IEEE754一致性未知；目标时钟/软件计时不可作为板上性能结论。
