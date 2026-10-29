# 执行记录：phase1a_plan.md

## T7：2026-10-28（原FP32/INT32四节点链完成，范围限定）

- 原9张量/4节点拓扑、shape/storage/常量和原输入锁定，复用T5/T6链路增加显式chains工作负载，默认samples保留、报告v3/nativeABI2不变。Python/NumPy/直接C/静态C/手算原与零输入对齐；每ELF单双发射、五次有效输出、13组契约检查。
- 新增第三节点FP32非有限/INT32溢出故障，完成2节点且最终输出不可见；恢复注入数据/输入后原与零各完成4节点。不提供整链物理回滚，与同步未知恢复分开。
- 新3项TDD通过，全部61工具通过；初验两链/4正向配置/20输出及4故障配置/8恢复输出通过、TCM阻断0。一次独立只读审查0问题、3项测试/真实日志/ELF/734产物哈希通过，无延期、不二次复审。
- 最终PC/目标两干净副本各322文件，无旧build，源/副本前后不变；PC174+61无跳过、54样本/双链/24压力200轮/原生含sanitizer通过。目标两原链均同ELF单双、20正向输出/8中途故障恢复输出正确，原/零结果[20,-25]/[0,-5]，最大绝对误差0，容量阻断/failed/unproven/tool_error=0；T6软浮点及原负控通过。
- 正向31744/BSS末34208，故障29952/BSS末31584；观察栈INT32 816/FP32 1120、故障656/1040，非最坏栈/板端预算。build/t7_validation_final/report.json、t7_final_integrity.json、t7_baseline.json/.sha256封存，新旧14阶段证据/核心/原链/冻结输入保持；54样本目标未重跑、实板/真实模型/任意链/其他故障/最坏栈/DDR等未知，不绑定模型/W4A8，不推送。

## T6：2026-10-26（FP32迁移完成，范围限定）

- 剩余27 FP32保持原shape/storage/物理字节，先核对FP32存储/FP64计算、ILP32 soft ABI、rv32im/ilp32 libgcc及有限边界探针；沿用冻结abs_plus_rel容差，单列bitwise及padding。单、双发射每例同ELF，原/零/原/恢复/rebind五输出，13组契约检查；新增非有限/溢出/原子性/恢复探针。
- 首轮新异常固件遗漏recover回调，bind失败，无trap；证据保留，补齐后初验27/27、阻断0、270输出通过，最大绝对误差0，观察栈1120字节仅为有限路径。FP32多节点目标链/实板/完整最坏栈等仍未知。
- 一次独立只读审查1 Important/1 Minor，未知证据误判failed与无输出误报等价；后者按用户要求重评Important，同轮两入口测试RED→GREEN，专项8/8，无延期、不二次复审。
- 最终三干净副本各317文件，无旧build，源/副本前后不变；PC174+58无跳过、54样本/双类型链/24压力/200轮/原生含sanitizer通过；FP32与INT32目标各27/27、容量阻断0。FP32单/双54配置、270有效输出、13组检查/额外边界故障探针通过，1296逐参考比较最大绝对误差0且逻辑逐位一致；INT32的27份ELF与T5指纹一致。
- FP32镜像30808—31544字节、BSS最高32736、样本观察栈1120，INT32观察816；不推断最坏栈/实板/OS或模型预算。汇总build/t6_validation_final/report.json，完整性build/t6_final_integrity.json，指纹build/t6_baseline.json/.sha256。旧13阶段收据/证据、109输入和核心/T5固件不变，FP32目标多节点整链/真实模型/实板等仍未知；不绑定模型/W4A8、不提交推送。

## T5：2026-10-26（INT32优先迁移完成）

- 用户授权INT32优先迁移，先同步S6能力/差距/接入文档口径。54冻结样本中INT32/FP32各27；FP32目标不在本轮范围。保持原shape/storage/数据，正向固件不嵌golden，PC两Python参考/直接C/独立静态C对齐后再比UART真实字节。
- 初验27例×单双发射通过，各5次有效输出，13组异常/生命周期检查；合成数值溢出和真实超TCM链接负控通过，真实样本阻断0。初轮PC构建返回路径适配错误已修复，旧过程保留。
- 一次独立只读审查2 Important，无Critical/Minor；缺失冻结样本和混合容量诊断门禁均已反例RED→GREEN，专项6/6，无延期，不二次复审。
- 最终PC干净副本174+50项无跳过、54样本/双链/24压力/200轮/原生及sanitizer通过；目标干净副本27/27同原shape/storage/物理输入INT32全部通过，阻断0，54个profile/270有效输出、每profile13组检查、合成溢出/真实超容量负控通过。两副本各312源/数据文件，初始无build，前后源指纹一致。
- 样本初始化镜像30808—31288字节、最高BSS末32480、观察栈816，均为受测布局/路径，不是模型预算/最坏栈。汇总build/t5_validation_final/report.json、基线build/t5_baseline.json/.sha256、完整性build/t5_final_integrity.json。原核心/旧12份阶段基线/109输入不改，实板/FP32目标/最坏栈等仍未知。

## T4收尾：2026-10-26（完成）

- 用户授权收口前次T4D审查的2项延期：参数汇总和历史措辞。新增9项参数同源生成两条实际-G命令、rtl_profiles/v1分别汇总两配置及负控，父报告同步；报告v2/runtime0.6.0/nativeABI2保持，legacy字段明确单发射弃用作用域。
- 三项参数/来源/未知状态回归RED→GREEN。README/复现指南/初次T4和T4D计划、报告统一分期，旧build报告/审查JSON/基线不回写。
- 独立只读审查1 Important（默认正向失败丢失分类）已新增2项入口/完整性测试RED→GREEN修正；1 Minor（矩阵次数）已按用户文档授权修正。专项共5项，无延期，不二次复审；审查者未独立执行，最终回归由实施者完成。
- 最终PC干净副本174+44项无跳过、54样本/双类型链/24压力/200轮/原生及sanitizer通过；RV32干净副本同封存SHA ELF，显式9参数单/双配置正向/负控、ABI/布局/观察栈752通过。两副本各305文件，无历史build，运行前后源与副本指纹一致。
- 收尾报告build/t4c_validation_final/report.json，指纹build/t4c_baseline.json/.sha256，完整性build/t4c_final_integrity.json；两项前次延期关闭，旧11份阶段基线及证据保持，历史80次矩阵本次仅核对引用。
- 此次若诊断相关源和全部证据哈希不变，只核对引用历史80次矩阵，不称重跑。PC/仿真/实板分开，未测项未知，不绑定模型/W4A8，原地保存不提交推送。

## T4D双发射后续定位：2026-10-26（历史验收）

- 首差异为退休序号1522/PC0x3f18 andi，而非最终CRC trap；观测到FIFO指令/元数据错位，错误同对RAW/WAW。
- 原始RTL/封存完整ELF在Icarus双发射通过；56字节最小ELF在原Verilator双发射失败、Icarus通过。结论限定Verilator5.032受测生成模型的FIFO更新排序，未证明CPU硬件缺陷。
- 本地兼容overlay将两个纯组合预解码函数值先接wire，不改归档/上游/ELF/双发射开关；原完整ELF和最小例通过，533119条完整轨迹逐条与原单发射一致。新增upstream/portable-metadata显式选择，主工具报告v2，运行时0.6.0/ABI2不变。
- T4D当时独立只读审查两项Important用3项RED→GREEN修正故障签名及实际轨迹完整性，2项minor当时延期、后续T4收尾已关闭，旧审查事实保持，不二次独立复审。
- 修复后最终矩阵40记录/80执行完成，Icarus全40通过、兼容Verilator两配置20通过，原始双发射9失败保留；两个完整正向533119行轨迹逐条一致，实际/dev/full写入失败退出2无DONE摘要。
- 最终PC干净副本174+39项无跳过、54样本/双链/24压力/200轮/原生及sanitizer通过；RV32干净副本同原SHA ELF，两配置正常/零输入/负控/ABI/布局/观察栈752通过。各301源/数据文件，无历史build，源与副本指纹不变。
- 当前汇总build/t4d_validation_final/report.json、基线build/t4d_baseline.json/.sha256、完整性build/t4d_final_integrity.json；旧T4证据保持，不推送，上游不改，不绑定模型/W4A8，实板/形式等价/综合时序/其他版本/最坏栈未知。

## 初次T4：2026-10-26（历史：原RTL/Verilator单过双失败，后续已定位）

- 原地准备SHA固定xPack15.2.0-1/GCC15.2.0工具链，显式RV32IM+Zicsr/Zifencei、ILP32软浮点；使用固定主仓库c1bc715完整RTL，未修改上游CPU。
- 新增裸机startup/linker、无堆INT32四节点链固件及真实qinglong_soc Verilator驱动，PC离线导出、RV32执行不依赖Python，时间/profile明确不可用。
- 同ELF对照：单发射正常/零输入通过、752字节观察栈；默认双发射trap cause5，根因未知，默认集成/部署受阻。64KiB TCM/8KiB栈为测试布局，不代表OS可用预算。
- 初验干净副本174+33项、54样本/双类型链/24压力通过，RTL独立源副本重建复现单发射通过/默认失败。
- 一次独立只读审查2 Important+1 Minor，后者因故障证据分类影响重评Important；同轮新增反例RED→GREEN修复完整工具链安装校验、严格负控摘要及未done异常分类。专项8/8通过，无延期小项，不二次独立复审。
- 审查后最终PC干净副本174+35项无跳过，54样本/双链/24压力、200轮2400任务/40故障扫描位置、6原生含3 sanitizer全部通过；`build/t4_pc_final/report.json`。
- 最终RTL干净副本重新从288源/数据文件构建，官方包6159文件/链接完整比对通过；RV32 ABI2/context144/布局/观察栈752与负控通过，默认双发射仍trap，部署未就绪；`build/t4_clean_final/report.json`。
- T4最终汇总/指纹入口`build/t4_validation_final/report.json`、`build/t4_baseline.json/.sha256`、`build/t4_final_integrity.json`。旧T1—T3及S1—S6历史不改，原核心/174测试/54样本不改。不绑定模型/W4A8，无实板/最坏栈/FP32目标执行结论，无提交推送。

2026-10-23，用户授权在指定目录落实 A1—A3。

- Ruling：使用用户明确指定的现有目录，不创建 worktree、不调整 Git。
  原因是目标目录为空且用户已指定交付位置；代价是新文件仍处于上层工作区，
  后续提交时需要单独整理。
- Ruling：先实现 Python 参考工具和接口说明，不提前实现 A4—A7。
  完整 C/硬件接口只描述契约，避免将文档设计误报成运行时实现。
- 预检：目录为空，无 AGENTS.md 命中；Python 3.12.14、NumPy 2.3.5 可用。
- A1/A2/A3 共用张量描述、算子形状规则、fixture-v1 和数值比较规则。
  约定本轮基础子集；其余格式返回 UNSUPPORTED。
- A1/A3 初轮：14 项测试因缺失实现失败；完成基础参考后 14/14 通过。
- A2 初轮：11 项测试因缺失 fixture 实现失败。
- 调试：Windows 沙箱默认 tempfile 目录对子目录访问返回 WinError 5；
  指定工作区内普通目录写入探针通过。测试临时文件改在 build/test-temp，
  清理前验证绝对路径仍位于该根目录内；不修改系统临时目录或权限。
- A2：完整 25 项套件通过。
- A3 集合/CLI：7 项新测试先观察缺失功能失败，完成后 32/32 通过。
- 补充非法输入测试复现超大整数容差的 TypeError、非对象 JSON 的 AttributeError；
  修复后完整 33/33 通过。均保留回归测试。
- A1—A3 实现完成（审查前）：生成冻结样本 54 项，三方核验 54/54 通过，
  报告 build/reference_report_pre_review.json；准备独立只读审查。
- 独立审查：0 Critical、1 Important、1 Minor。Important 为 FP32 边界舍入，
  本地独立复现后新增回归 RED；改为转换后检查有限值，单项 GREEN。
- Final: fixed FP32 边界误拒绝 — test_fp32_boundary_is_decided_after_rounding
  RED→GREEN；2026-10-24 完整套件 34/34 通过，无跳过。
- Final: minor (deferred)：比较器直接比较零维 ndarray 失败时无首个坐标；
  fixture-v1 禁止零维，当前输入链不受影响，留待后续比较器接口收口。
- 审查判定：共享校验、FP64 归约差异、可配置容差、非认证哈希和中断后的残留目录
  按文档约定保留。代价是未来更强数值/真实性/事务或并发保证需单独设计验证；
  不扩大本阶段结论到真实模型、C/RTL/硬件。
- A1：complete，契约和基础检查完成；完整会话/设备接口仅为设计。
- A2：complete，fixture-v1 规范、读写及负面校验完成。
- A3：complete，两个参考与三方核验完成；54/54 样本，162 项比较通过。
  最终证据 build/unittest_post_review.log、build/reference_report_post_review.json。

## A4：2026-10-24

- 用户授权继续在本目录实现 PC 最小 C 算子调用链，不绑定模型或 W4A8。
- 使用 executing-plans、test-driven-development、verification-before-completion 工作流；
  按要求完成独立只读代码审查及问题复核。
- 实现 c/ C11 ABI/核心/直接测试、ctypes 绑定、verify-c、构建及验收报告。
- 初始 10 项新增回归先因缺失功能失败，核心完成后通过。
- 独立审查发现计数器别名及链数值失败报告中断，新增两项回归先复现再修复。
- 最终：46/46 完整测试无跳过，54/54 冻结样本、162 项 C 比较通过，
  INT32/FP32 两条四节点 C 链及逐节点/手算最终值通过。
- 直接 C ASan/UBSan 实际执行通过；环境 WSL Ubuntu x86_64、GCC 15.2.0。
- A4：complete。最终证据 build/a4_validation_final/report.json、build/a4_unittest_final.log；
  说明 docs/c_backend.md、docs/a4_validation_report.md。不改原冻结样本或其他项目，不提交推送。

## A5：2026-10-24

- 计划：docs/a5_plan.md；用户明确授权直接继续 A5，沿用指定目录和原数值规则。
- Ruling：PC Python 解析数据包和规划静态 arena，再直接绑定 A4 C ABI；
  不引入模型框架/ONNX，不把本轮交付称为板端 C 包加载器。
- Pre-flight：包图规格 -> 不可变 MemoryPlan -> 共享 CTensor/CCall；闭区间和独立 scratch
  对齐 A4 别名限制，padding 独立槽对齐零 padding 检查。
- 原 46 项 A1—A4 基线通过；包/内存 14 项 RED -> GREEN；运行时 8 项 RED -> GREEN。
- CLI 先复现缺失 verify-packages，接入后端到端通过；非普通文件回归 RED -> GREEN。
- 补充固定种子 24 个 8 节点分支图，混合 padding/提前输出，各重复运行 2 次通过。
- Ruling：预算包含实际 backing 的 alignment-1 额外空间，排除包 bytes/对象/输出副本；
  保持预算语义准确，代价是它不是进程 RSS 或多会话全局上限。
- A5 专项当前 24/24 通过；准备完整回归、正式验收报告和独立只读审查。
- 审查前完整 70/70 无跳过；54 包/162 比较通过，原 109 文件哈希不变。
- 独立只读审查：0 Critical、0 Important、1 Minor；独立字段类型/后段失败重试/释放探针通过。
- Final：非法根路径 ValueError/TypeError 泄漏新增回归 RED -> GREEN，统一 ContractError。
  本轮一遍修复，原问题有回归覆盖；不调整其他模块或原 C 核心。
- A5：complete。修复后完整 71/71 无跳过，54/54 包、162 比较、两条四节点包和原生
  C ASan/UBSan 通过；最终源码/二进制/样本哈希已核对。
- 内存例：激活 arena 320 -> 128 字节，总 backing 829 -> 637 字节；仅小型静态合成图。
- 最终证据 build/a5_validation_final/report.json、build/a5_unittest_final.log；
  接口 docs/model_package.md，说明 docs/a5_validation_report.md。未提交/推送，不改其他项目。

## A6：2026-10-24

- 用户授权续做模拟设备与任务生命周期；计划 docs/a6_plan.md，规格 docs/sim_device.md。
- Ruling：在指定目录原地实施，不创建 worktree/提交推送；延续已批准契约直接执行。
- Ruling：单所有者线程、逻辑 tick、显式推进，实际数值调用 A5 run -> A4 C 链；
  代价是不验证真正并发/硬件抢占。无后台线程和隐藏 Python 回退。
- A1—A5 71 项基线通过；A6 初始 15 项因缺失实现失败。
- 核心实现后 14 项通过，CLI 缺失明确 RED；加入口后 16 项通过。
- 未注册 SimSession 可绕过 lease 的回归 RED -> GREEN，加入设备注册校验。
- 所有权：提交成功后私有快照，持有整个会话 lease；结果可见且终态静止才 release。
  TIMEOUT 不终结任务，取消未确认/隔离状态不释放；恢复必须模拟器确认。
- 进一步验证输入/输出 weakref 释放及一个错误结果让报告失败/CLI=1；准备完整验收和独立审查。
- A6 专项 18/18 通过；审查前完整 89/89 无跳过，54/54、162 比较、双链和 8 场景通过。
- 独立审查：0 Critical、0 Important、1 Minor，为 C 返回后主机异常导致完成计数丢失。
- Final：新增真实 C 异常进度回归 RED -> GREEN；execution_id 区分本次/历史执行，
  入口异常保持 0/未知且隔离；没有以旧记录或带状态异常推断设备已静止。
- A6：complete。修复后 90/90 完整测试无跳过；54/54、162 比较、两条四节点链、8 场景和
  原生 C ASan/UBSan 通过。最终任务/会话/staging 为 0；源码/二进制/输入哈希已核对。
- 最终证据 build/a6_validation_final/report.json、build/a6_unittest_final.log；
  规格 docs/sim_device.md、说明 docs/a6_validation_report.md。未提交/推送，不改其他项目。

## A7：2026-10-24

- 依据用户明确授权，原地落实已确认 A7；计划 docs/a7_plan.md，规格 docs/tracing.md。
- Ruling：有界元数据收集器，不保存数值；host perf_counter、C process CPU、逻辑 tick 分离。
- Ruling：可选 C profile ABI，原普通链不变；profile 与模型 arena 分离，计入追踪额外内存。
- 原 90 项基线通过；初始 9 项及直接 C 缺接口 RED；录制器/C/runtime/device 分步 GREEN。
- 关联/畸形文档/CPU 算式负面对照 RED -> GREEN，专项 12 项通过。
- 真实旧 A6 .so 验证普通计算兼容，缺失逐节点能力时 trace 不完整，未以 Python 数值回退。
- 正式准备：54 样本追踪开关逐字节一致、双链、8 场景、观察失败/溢出和导出回读；
  正在完整回归和独立审查，不提交推送。
- 审查原 1 Important（语义遗漏/矛盾误通过）与 1 Minor（提交缺关联）已修复；
  缺失 run.end 的错误处理回归 RED -> GREEN；独立复验无剩余 Critical/Important。
- 最终 A7 专项 15 项，完整 105/105 无跳过；54/54、162 比较、54 开关逐字节对照、
  双类型链、8 场景、2 观察故障探针、8 语义负面对照及 C ASan/UBSan 通过。
- A7：complete。主追踪 2978 事件，无丢失/采集错误，导出回读一致；源码/二进制/109 样本哈希核对。
- 证据 build/a7_validation_final/report.json、build/a7_unittest_final.log；
  规格 docs/tracing.md、说明 docs/a7_validation_report.md。未提交/推送，不改其他项目。

## S1：2026-10-24

- 用户授权基线固化，计划 docs/s1_plan.md，统一入口 docs/phase1a_baseline.md。
- Ruling：指定目录原地修改，不动上层其他项目/变动，不创建 worktree、不提交推送。
- Ruling：仅工具补丁 0.1.1 与文档契约修订 v0.1.1；磁盘格式 version=1 / C ABI=1 不变。
- Pre-flight：build/s1_preflight.json 保存原 162 文件指纹，其中 109 个冻结文件；C 核心不修改。
- 根因：零维失败 argwhere shape=(1,0)，size=0 不能用于判断不存在坐标行。
- 两项新增回归先观察 7 个子场景坐标失败；改为按行数判断后，Windows 参考专项 17/17 通过。
- 覆盖整数/浮点标量、相等、容差、NaN/Infinity 与 JSON 安全；fixture/算子 rank 支持不扩展。
- 正在进行完整 WSL C 回归、新版本端到端验收和一次独立审查。
- 完整 107/107 无跳过；工具 0.1.1 端到端 54/54、162 比较、双链、8 场景、
  2 观察故障探针、8 语义负面对照及原生 C ASan/UBSan 通过。
- 109 冻结文件与 c/ 源码/测试指纹不变；新源码指纹核对通过，主追踪 2978 事件完整。
- 进入一次只读独立审查；审查后固化 build/s1_baseline.json 版本/文件/证据指纹。
- Final：独立审查代理因额度限制在审查前退出，无审查结论；用户明确授权如实记录限制并继续。
- Final：作者自查比较器/测试、版本与边界说明、新旧证据和修改范围；额外 10 个
  rank 0—4 / FP32 / INT32 首坐标探针通过，不等同于独立审查。
- S1：complete（独立审查不可用的限制已披露）。固化 build/s1_baseline.json 与
  build/s1_baseline.sha256，收录 56 个项目文件、109 个冻结输入和本轮验收证据指纹。
- 本轮 13 个已有文件修改、3 个文档新增，无删除；未提交/推送，未实施 S2—S6。

## S2：2026-10-24

- 用户授权可替换静态整链后端，计划 s2_plan.md、规格 backends.md；指定目录原地，不提交/推送。
- Ruling：默认禁回退，仅 query 明确不支持且 allow_fallback=true 时按声明顺序尝试；
  配置/损坏报告/查询/prepare/运行失败不触发重选；不做自动切图。
- Ruling：工具 0.2.0 / Python 后端 API 1 / 文档契约 v0.2.0；磁盘 version=1、C ABI=1 不变。
- 后端需求/能力/注册表与策略；C ctypes 绑定抽离到 c_execution.py，旧 CBackend 调用兼容。
- 初始 7 项 RED -> GREEN；generic 追踪/后端篡改/未知执行复用/只读输出先 RED 后修复。
- 未知执行必须隔离同步会话与 task，后端确认后恢复；拒绝恢复保留 lease/staging。
- 未知错误占位状态回归 RED，修复为 DEVICE_ERROR；数值首段/后段失败保留 0/3 完成数，不重跑。
- 审查前完整 125/125 无跳过；54/54、54 次显式回退、162 比较和原 A7 全路径通过。
- 待独立只读审查和最终复验；证据使用新 build/s2_*，不改 S1 清单/冻结样本/C 核心。
- 独立只读审查 0 Critical、2 Important、0 Minor；无隐藏重跑，确认恢复/关闭异常保护边界。
- 一次修复：generic DEVICE_ERROR 的节点间/收尾语义，以及删除会话身份字段绕过校验；
  两项回归均 RED -> GREEN，CLI 增加两种选择身份负控，不做第二轮独立审查。
- S2：complete。最终完整 127/127 无跳过，S2 20 项；54/54、162 比较、54 次显式回退、
  原双链/8 场景/观察故障/8 负控与实际 C ASan/UBSan 通过，两设备资源归零。
- 主追踪 4378 事件，原运行时追踪 3046 事件，完整且回读通过；源码/二进制指纹核对。
- 证据 build/s2_validation_final/report.json、build/s2_unittest_final.log、build/s2_baseline.json；
  规格 backends.md、结果 s2_validation_report.md；S1 清单/旧证据、109 输入及 c/ 全部不变。
- 未提交/推送；未实施 S3—S6、真实模型/量化/硬件或自动异构切图。

## S3：2026-10-24

- 用户授权模型无关平台服务，计划 s3_plan.md，规格 platform.md；原地实施，不改其他项目或提交推送。
- 工具 0.3.0 / 平台 API 1 / 后端 API 1 / C与磁盘 1；PC实现不等于板端 C 或 RV32 执行。
- 初始8原语 RED；6集成因缺平台参数 RED；接入后14/14专项通过，原全量141/141通过。
- 追加并复现部分释放重跑、删除同步记录误通过、读MemoryError漏分类、直接坏时钟未标不完整、
  动态来源size重取可绕过限长；均修复并保留回归。
- 模型weak借用/显式close、分配失败回滚、未知同步保留arena/lease、独立恢复确认；GC兼容。
- 新verify-platform先复现缺入口，接入54样本/162比较、5故障边界探针和嵌套S2/A7实际C验收。
- 22项S3专项，正在审查前全量149项与端到端验证，随后一次独立只读审查。
- 审查前149/149无跳过、54/54/162比较与5探针、嵌套S2/A7/C sanitizer通过。
- 独立只读审查0 Critical、2 Important、1 Minor；同步context错配按验收影响升级Important，同批处理。
- 三类回归先RED：整个对象图GC逃逸、binding.close失败重跑、五类同步context错配。
  一次修复强保留/可找回入口、关闭状态双标志、run完整context匹配；不做第二轮独立复审。
- S3：complete。最终152/152无跳过，25项S3；54/54、162比较、5探针、同步缺失/错配负控通过，
  嵌套S2/A7与实际C ASan/UBSan通过；主追踪3458事件完整，内存/文件/隔离登记和设备资源归零。
- S1/S2清单与旧证据、109冻结文件及c/不变；当前源码/C源码/库/原生测试二进制指纹一致，
  旧S1/S2追踪回读验证通过；固化 build/s3_baseline.json / s3_baseline.sha256。
- 结果 s3_validation_report.md、规格 platform.md；未提交/推送，不做S4—S6或真实模型/量化/板端验证。

## S4：2026-10-25

- 用户明确选择PC离线检查/规划、导出执行描述/权重、C绑定arena执行；原地实施，计划s4_plan.md，规格static_runtime.md。
- 新IRS4BIN1小端无指针格式与CRC；原ir_core/既有ABI和格式不变；工具0.4.0，static runtime API1。
- 导出器/原生runtime/PC平台/适配器先缺失RED；逐步接入后专项通过，独立C进程在无Python PATH执行。
- 补齐重绑未知上下文、allocator所有权、每次重新供应输入、padding、数值0/3节点失败等回归。
- 首轮54/54/162比较、双链及sanitizer通过；审查前完整159/159无跳过。
- 独立审查0 Critical/3 Important/0 Minor；旧block读取误释放、重复分配泄漏、部分输出残留各先RED再一次修复；无独立复审。
- 最终161/161无跳过，S4专项9项；54/54/162比较及54次独立/适配逐字节一致，双链正常/零输入、ASan/UBSan和5追踪负控通过。
- 适配追踪3786事件完整；C与Python平台/设备资源归零；原109输入、ir_core和S3历史清单/证据不变；当前源码/二进制指纹核对。
- S4：complete。证据build/s4_validation_final/report.json、s4_unittest_final.log和s4_baseline.json；结果s4_validation_report.md。
- 未提交/推送；仅PC验证，无RV32/板端DMA/cache证明，不绑定模型或W4A8；S5/S6未实施。

## S5：2026-10-25

- 用户授权运行时资源账本和压力测试；原地实施，计划s5_plan.md，规格resources.md。
- 工具0.5.0/ResourceLedger API1；C PC具体结构services ABI2需重编译，原core/磁盘/函数表API1不变。
- 受管载荷/记录计量非RSS；arena、原生元数据/固定inspect工作集、profile、trace缓存、task staging/record/event与Session记录分开计账。
- 初始接口/集成/原生/CLI RED；未知Device对象图GC丢失任务资源先复现，增加强持有/可找回/确认恢复释放；history设上限。
- 预审首轮171/171无跳过；24/24压力探针与54样本/双链/sanitizer通过。
- 独立只读审查0 Critical/2 Important/0 Minor；临时CCall/shape原生载荷漏账、可选profile挤占必需stack预算；两项RED后一次修复，不独立复审。
- S5：complete。专项13/13，最终174/174无跳过；Windows基础5/5；24/24压力、2400重复任务、40故障位置、两后端各50拒绝恢复和close重试后归零。
- 原生C普通/ASan各1000次小链及6个分配失败点通过；嵌套54/54/162比较、双链及3786事件追踪通过；62份C分类账目核验。
- 证据build/s5_validation_final/report.json、s5_unittest_final.log、s5_baseline.json；说明s5_validation_report.md。不绑定模型/W4A8，不提交/推送，不做S6或硬件验证。

## S6：2026-10-25

- 用户授权候选需求/检查清单与当前能力差距整理；不新增执行支持，工具仍0.5.0，资料/模板v1。
- 新增model_intake/capability_matrix/model_gap_analysis/model_memory_requirements及4份空白需求模板，未知保持null/pending。
- 逐项梳理算子/属性、存储-计算-累加-output dtype、量化方程与packing、物理布局、状态/profile与完整内存分项；不预设模型/W4A8。
- 实际审计54/54，两后端108样本query与324样本参考比较，双类型四节点链；28类两后端拒绝和初始7项包/预算/地址负控通过。
- 独立只读审查0 Critical/1 Important/2 Minor；后三者对应padding准入描述、转换状态矛盾、query/plan顺序，作者按文档验收影响将两Minor升级Important，同批修正。
- 追加实际FP32负零padding两后端正控、数值非零padding负控；最终8负控、链/负零补充18比较及全审计通过，资源归零；无独立复审。
- S6: complete。55份运行时/C/tests与109冻结输入不变；S1—S5历史收据/证据核验；未本轮重跑174全量或sanitizer，不混同历史结果。
- 证据build/s6_validation_final/report.json、s6_baseline.json；说明s6_validation_report.md。无真实候选/目标数据时整体pending；未提交/推送。

## T1：2026-10-25

- 用户授权无需历史build的可复现单入口；运行时仍0.5.0，新工具v1，原地不提交/推送。
- tools/reproduce→快照/空build→run_tests/verify-resources/audit_intake→统一结果/指纹；原174ID与测试源指纹固定，工具测试单列。
- 初始6工具RED；数值/身份/重复链门禁补测RED→GREEN。初审新副本174/174+7工具通过，源216/产物1044。
- 自查额外源/拒绝已有输出写报告两个问题先RED再修复，工具9项；独立审查0C/3I/1M。
- 一次修复sanitizer日志漏判、压力/执行证据不足、环境覆盖；超时后代写产物按证据稳定性升级Important并同批修复。
- 新回归RED→GREEN，真实可恢复UBSan退出0仍拒绝、进程组超时清理通过；无第二轮独立审查。
- T1: complete。最终全新t1_final：174/174和工具14/14，无跳过；54/54、双类型四节点链正常/零输入、24项200轮压力及普通/ASan/UBSan、S6审计通过。
- 源218/产物1046指纹、受测快照/原源完成时集合一致，原55runtime/C/tests及109输入不变，S1—S6历史证据核对。
- 证据build/t1_final/report.json与report.sha256、t1_integrity_checks.json、t1_baseline.json；文档reproducible_build.md/t1_validation_report.md。
- 最终统计收尾仅更新文档，代码/输入与受测快照相同；未提交/推送，不绑定模型/W4A8，无RV32/板端验收。

## T2：2026-10-25

- 用户授权目标平台约束核对，原地执行不提交/推送；不绑定模型/W4A8，不改变运行时0.5.0。
- 固定主仓库c1bc715的27文件，PDF原始资料/现有平台源合计43来源，形成54约束/9领域/13未知；6类目标预算null。
- 确认64KiB TCM/最小8KiB栈预留，DDR未映射；发现32KiB检查器局部工作集、20KiB context数组；均非目标测量。
- 当前探测未找到交叉GCC，不安装/上板；新核对入口，预审工具19/19无跳过。
- 独立只读审查0C/1I/0M：来源集合/blob/固定提交门禁不完整；新增反例先FAIL，修复并校正中文URL编码，最终工具20/20无跳过，不独立复审。
- T2 complete（约束核对范围）。最终Windows/新259输入干净副本审计通过；43来源/27远程blob及提交索引一致，13未知/6预算null保持；未执行目标编译或硬件。
- 55 runtime/C/tests、109输入、全部170旧受测代码/输入和S1—T1历史证据指纹不变。本轮未重跑174/54样本/双链/压力，最近完整结果仍为T1。
- 证据build/t2_validation_final/report.json、t2_final_integrity.json、t2_baseline.json；说明target_platform_constraints.md/t2_validation_report.md。收尾仅更新文档，不提交/推送。

## T3：2026-10-25—26

- 原地实施运行时0.6.0/native ABI2；不绑定模型/W4A8，不提交/推送，磁盘/ir_core ABI/函数表保持。
- context固定数组改caller-owned T字节state，inspect改4T字节临时区；保留4096/1024上限，_v2入口和ABI查询，旧调用方重编译。
- 原174/174、工具26/26及首轮54/双链/24项200轮压力通过，但S6公式漏T导致整体失败；修正后S6复验通过，旧失败证据保留。
- 同GCC PC sizeof20672→200，inspect frame32928→192、bind448→480；T2九份旧框架源固定保存，目标工具链/布局/栈峰值仍未知。
- 独立只读审查0C/1I/1M；profile失败四组合先RED后降级GREEN，容量文档限定元数据前缀/arena整段，工具27/27无跳过；不独立复审，待最终新副本与收据。
- T3 complete（PC范围）：最终t3_final顶层passed/exit0，原174+工具27无跳过，54/双链/24项200轮压力/普通与sanitizer/S6/T2来源/PC元数据审计全部通过。
- 新副本274输入、1116产物；原174测试源/109输入/ir_core与T2九份旧源保护，S1—T2历史收据和证据核对。源完成时一致，收尾仅更新文档。
- 证据build/t3_final/report.json、t3_validation_final/report.json、t3_final_integrity.json与t3_baseline.json/.sha256；目标工具链/布局/栈峰值未知，不绑定模型/W4A8，不提交/推送。
## T8：2026-10-28

- 用户授权当前版本统一总验收；运行时0.6.0/native ABI2不变，C核心/固件/冻结样本/链定义/RTL选择不变，不绑定模型/W4A8。
- 新tools/reproduce_total→同一源码干净副本，PC空build全量→all混合dtype54原样本+2原链，重新构建单/双RTL和各ELF；逐项重读实际PC/ELF/UART/参数/原输入权重证据。
- 新报告分56主项、额外软浮点/溢出/容量、主机日志反例、PC和实板；passed/blocked_tcm/failed/unproven/tool_error保留三值；仅全部通过exit0。
- 初始6门禁与自查3门禁先RED后GREEN；独立只读审查0C/5I/0M，一次修复新增7回归先RED后GREEN，专项16/16；不独立复审，最终全量/基线待封存。
- 首轮会话中断、预审PC174+70通过后主动停止目标进行审查修复，两次诊断均不冒充最终总验收。
- 首份t8_final PC174+77/目标56通过但边界重放漏storage_shape，tool_error/null/exit1保留；新回归复现TypeError后修复，专项17/17。
- 最终t8_final_verified总入口passed/exit0：原174+工具78无跳过，54样本/两链×原零/24项200轮压力/6原生含3sanitizer通过；同新副本原56项RV32同ELF单双112配置/560输出、4链故障配置/8恢复输出、6额外配置、112同步未知及真实容量负控通过。
- 主56项blocked_tcm/failed/unproven/tool_error全0，保留原形状数据；source328/artifact4070、原源和副本完整、无历史build。实际产物主机5反例通过，均不冒充目标执行。实板/完整最坏栈/模型等未知，不绑定模型或W4A8，不提交推送。
- 旧15阶段收据及20229次历史证据哈希核验通过；仅3文档运行后收尾，最终219源码+109冻结输入及完整产物指纹由build/t8_finalize.py核验封存。入口报告t8_final_verified/report.json，汇总t8_validation_final/report.json，基线t8_baseline.json/.sha256。

