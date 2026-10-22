# 执行台账：A小用例PDS接入与K256实板验证

用户授权：两套小用例接入PDS，先完成K256全构建及验证，再实板UART采集。
保留原Qwen工程和位流；不commit/push。沿用codex/b-multigroup-uart-cases当前目录。

## 原文件保护基线

- Qwen prj.pds SHA256：01b3a57690bf9f474ae5ee4170f8bd943b6e34d8d7e023ee93354cb907f7cb6c。
- Qwen UART sbit：718330d02168d8a9af8ed09f5d24bc70e69eaad67431faef7639c3c7382eef16。
- Qwen LED-only sbit：a88f723e176161d68cffa66a776777ba79966d4eda0d467454dc7991ead6cb6b。
- 原未提交给A回复文件保留，不改动。

## 执行计划与门槛

1. 复核两套输入/仿真证据；为固定N3/K256和N3/K384建立独立顶层与工程。
2. 使用同一UART TX采样BFM验证真正的PDS顶层及维度，先失败后实现。
   仿真覆盖ROM路径以读取build数据；生产mem路径另以PDS加载日志和逐文件哈希验证。
3. 只运行K256的Compile/Synthesize/Device Map/PNR/Report Timing/Bitstream。
4. 检查错误与关键警告、27MHz时钟、7个已约束IO、资源、setup/hold裕量及位流哈希。
5. 全部通过后，才允许将K256 sbit下载到FPGA CRAM（不写Flash/eFuse）。
6. 实时枚举CP2102、打开UART接收后由用户按KEY0，分别采集3次6条/57字节。
   每次逐项比较row_id/group_id/partial_sum、原始帧，记录用户确认LED状态。
7. 保存本轮构建/下载/采集证据并再次校验原Qwen基线；用户未要求本轮构建/下载K384。

Pre-flight：转换ROM的32路物理打包经B适配器转16路；N3/K256需要6条，K384需要9条。
独立工程各有mem目录，顶层名称不同，不能复用Qwen默认N16/K2048或其输出位流路径。

Ruling：遵循用户已选当前目录/独立分支，不创建worktree；隔离在新增fpgatest目录。
代价：工作区包含上轮未提交仿真文件，必须按文件清单区分，不能提交整区。
Ruling：只配置K384工程，本轮先构建/下载K256；避免切换板端配置而混淆采集来源。
Ruling：批处理优先使用已安装PDS官方pds_shell及cdt_cfg_shell，窗口用于确认工程和报告。
代价：GUI未自动反映批处理结果时需重新打开独立工程；不得保存/重构建原Qwen工程。

状态：两套固定顶层的真实TX波形仿真已通过，三次复位及发送中复位恢复通过。
已观察新增顶层缺失时的编译失败，再新增封装通过；未更改Qwen计算逻辑。

构建诊断：官方shell的-file模式先解析脚本再执行；解析时pwd是启动目录而非-work_dir。
首次从仓库根启动导致错误顶层qiansai_FPGA_uart_board_top；该次未生成可下载位流。
Ruling：初始化脚本使用显式PDS_A_PROJECT_DIR，且shell工作目录和-work_dir都设为独立prj；
-file只用于创建基础工程，完整构建使用已选择ADS/SystemVerilog的显式-project工程入口。
初次-file全流程仍在预解析阶段提示未选择综合工具，虽然随后运行到位流，不能混作干净构建。
按系统调试技能读取生成.pds/impl.tcl/run.log确认后，独立-project全构建无E/C错误。
许可：当前工具进程未继承用户PANGO_LICENSE_FILE，仅为本次shell子进程继承用户已配置值，
未修改用户/系统环境和许可文件。

独立审查：无Critical。Important：GUI helper只验证env标签却操作活动工程，接受并修复。
移除该helper，改为build_a_multigroup_pds.ps1显式-project入口；两个正常预检先因缺少入口
失败，再实现，另验证只允许256/384，并校验每套4份ROM/config哈希。
Minor（延期）：缓存忽略规则尚未包含generate_netlist/report_power/flow.log；均为PDS生成物，
不影响构建功能，本轮归档按允许列表排除这些缓存，不自动提交整个工程目录。
文档中的生产ROM路径证据和最终复现入口已补充，消除误导。

已通过：19阶段RTL回归，K256/K384固定顶层TX仿真。
K256官方直接-project构建完成于2026-10-21 21:53:05（北京时间），包括Compile、Synthesize、
Device Map、PNR、Report Timing、Generate Bitstream（还自动运行Power/Netlist）。
时序All Constraints Met：27MHz，setup最差24.910ns，hold最差0.105ns，失败端点0。
综合858 LUT/528 FF/16 APM/2 DRM/7 IO，Latches=0；IO全部已定位，UART=C24。
位流3791112字节，SHA256 9f52c78c1d42c598e7e442aab9d7f15da7be9efe141a3d83aac228ecc26bb160。
K384独立工程已配置ADS/SystemVerilog及固定顶层，未综合/生成位流。

硬件状态：初次仅COM1；用户接回后实时枚举CP2102 COM10（10C4:EA60/0001），
下载器FTDI COM8/COM9。官方只读扫描PG2L100H、ID0x00602899。
已下载本轮K256 CRAM，done=1、状态0x081ffca0，timeout/rbcrc/aut/crc/id错误位均0；
不写Flash/eFuse。程序日志绑定同一.sbit路径，编程前重新核验9f52c78c...位流哈希。
第一次COM10真实采集6条/57字节，row/group/sum逐项匹配，用户确认LED1/2亮、LED3灭。
三次均实际KEY0复位后采集，6条/57字节，三帧SHA256均
028ca79b4385aa6ad78a08a066e02f72bef9cd0bccf67382dcdbc24c8106c577。
每轮用户确认LED1/2亮、LED3灭；LED/复位来源是用户确认，不是UART协议内字段。
来源board与simulation严格区分；证据冻结到evidence/a_multigroup_pds/2026-10-21/k256。

警告处置：compile明确加载隔离prj/mem三文件，实际输出匹配原始A整数golden。
activation_mem/expected_mem的Sdm-2003是静态初始化ROM无运行时赋值的分析提示，
综合网表保留非零初始化DRM（weight_mem）和驱动activation的初始化LUT；本轮实板数据
进一步核验对应行为。不能仅凭综合资源或RTL仿真宣布ROM内容正确。
Timing-4086/4087为异步KEY0/LED/UART接口建模提示；KEY0/LED有false-path，
UART有37.037037ns max-delay，内部时钟setup/hold全满足，不任意伪造外部同步时钟。
最终审查不覆盖完整后综合形式等价；本轮以固定fixture的实板逐项结果为功能验收边界。

Final: fixed GUI活动工程风险——移除GUI helper；Windows显式工程预检2项RED→GREEN，
3/3 Windows预检通过；修复后19/19回归通过（WSL 55项通过、3项Windows专用跳过，
对应3项已在Windows实际运行通过）。没有新增Critical或Important未解决项。
Final: Ruling: 审查未判断的ROM警告——已用加载日志/初始化网表/三次真实6条输出闭环，
不改动原计算RTL；代价是仅证明本fixture，不代表完整模型或任意向量形式等价。
Final: Ruling: 审查未判断的硬件/LED——本轮已实际下载和采集，LED依用户三次确认；
协议无位流ID/LED字段，不能通过UART自证位流身份。
Final: Ruling: K384综合未纳入本轮——按用户先K256顺序，仅配置并仿真K384；
代价是K384还不能宣布PDS/实板通过。
原Qwen .pds和两份.sbit最终哈希均与本轮开始一致；未commit/push。
GUI切换遇到用户输入保护/最小化，未继续强制抢焦点；工程可通过PDS Open Project打开，
本轮构建、报告检查和下载均已有官方批处理实际证据，不宣称窗口已自动显示新工程。
