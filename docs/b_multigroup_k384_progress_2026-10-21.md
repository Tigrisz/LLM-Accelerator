# 执行台账：K384完整构建与三次实板UART

用户授权：独立K384工程完成Compile/Synthesize/Device Map/PNR/Timing/Bitstream，
通过后下载到CRAM，三次KEY0重跑，逐项比较9条标签和部分和；不commit/push。
原Qwen、K256工程、ROM、约束、位流、K256冻结证据均按执行前哈希保护。

计划：
1. 校验N3/K384、group128、capture深度9和4份ROM/config哈希。
2. 用既有显式-project入口构建K384，不通过GUI修改其他工程。
3. 检查无E/C错误、三份ROM加载路径、27MHz时钟、7个IO、资源、setup/hold裕量。
4. 只读扫描PG2L100H；构建通过并绑定位流哈希后才下载CRAM，不写Flash/eFuse。
5. COM10逐次打开接收，由用户按KEY0，三次各9条/81字节，与PDS golden、A原npy、
   原始打包数据独立整数重算及A仿真参考逐项比较；LED由用户确认，不从UART推断。
6. 独立审查与冻结证据，检查原保护清单不变；只交付本轮结果，不提交Git。

Pre-flight：本轮不改计算RTL或接口；复用上一轮已验证的K384固定顶层/独立PDS配置。
ROM物理打包32路，经现有B适配器转16路计算；N3、每行3组，必须恰好9条。
原A包是确定性合成用例，不是Qwen真实模型切片；capture参考是simulation。

Ruling：沿用用户已选择的当前目录和codex/b-multigroup-uart-cases分支，不新建worktree。
代价：工作区包含前两轮未提交文件，最终不能把全部工作区误认为本轮新改动。
Ruling：使用官方命令行显式-project入口，不重复GUI切换。代价：不保证GUI自动显示K384。
Ruling：不重写生产RTL，仅运行已有K384设计及配置；若发现故障才按RED/GREEN修复。

已完成：Windows显式工程入口3/3预检测试通过；K384预检N3/K384/9记录及4份哈希通过。
原保护文件已实时归档到artifacts/a_multigroup_k384/2026-10-21/protection_baseline.json。
硬件实时枚举CP2102 COM10，下载器FTDI COM8/9；尚未下载K384或采集其数据。

调试：首次全构建在gen_bitstream出现C:Bitstream-2001，SCBV未设置，门槛失败，
即使工具退出码0且输出.sbit也不下载。按systematic-debugging对比已验收Qwen/K256设置，
确认本K384工程缺少scbv字段；只在K384 .pds补上High Voltage，并设compile force_to_run，
重新执行完整流程，以实际无C/E日志作为GREEN证据。初次日志单独保存，不混入验收日志。
Ruling：SCBV沿用相同板卡的已验收High Voltage配置，不改引脚/时钟/RTL；
代价：仅适用于当前已知开发板，换板必须重新核对配置bank电压。

修复后K384完整构建已通过，无E/C诊断；所有六个阶段完成。
27MHz、All Constraints Met，最差setup24.087ns、hold0.103ns、失败端点0。
917 LUT、613 FF、16 APM、2 DRM、0 Latch、7 IO全部定位，UART=C24。
三份ROM均明确从本K384 prj/mem路径加载。原77份保护文件逐一哈希未变。
只读JTAG确认PG2L100H、0x00602899；接下来只下载本轮通过检查的K384位流。

最终K384位流3791112字节，SHA256：
357bd0201b621faf553c3c46b3d750c9e3bc23348252c258f6029f14fe7efb94。
已成功下载到CRAM，done=1、状态0x081ffca0，timeout/rbcrc/aut/crc/id错误位均0。
修复后19/19完整回归通过；Windows3/3工程预检通过。
COM10三次实际KEY0复位采集全部完成：每次9条/81字节，row/group/sum逐项通过，
三帧逐字节一致，SHA256：9e0277e49852d894561765c6f4896fbb19ad953bb6ee5d23e27c42395151eda4。
用户分别确认三次LED1/LED2亮、LED3灭；该观察来自用户，不是UART协议内字段。
PDS/RTL/下载/原始采集证据归档至evidence/a_multigroup_pds/2026-10-21/k384。
最终来源/全文件哈希复核通过，不commit/push。

Final review：独立只读审查PASS；无Critical/Important。
审查独立重算原始INT4/INT8、解析NPY、解码三帧，9条结果全部匹配；
49份冻结文件、141项回归源文件指纹、77份保护文件均无哈希差异。
Final: minor (deferred): 每轮接收命令输出/操作确认时间戳尚未单独冻结，
未来可增强独立审计便利性；不伪造本轮未记录的精确时间。
Final: Ruling: 实板来源依实际COM10会话和用户确认——字节等同仿真不能自证来源；
代价：离开本会话的独立审计需要信任采集来源记录。
Final: Ruling: UART不含位流ID/LED字段——保留程序路径/哈希及用户三次确认，
不虚构协议自证；代价：不能通过UART单独证明位流身份或LED状态。
Final: Ruling: 不解释over_temp=1、不测量配置bank电压、不作任意输入/后综合形式等价，
不审计无关工作区改动——这些超出固定用例功能验收；原始状态字保留，
不能将本轮通过扩大为温度/电气/任意输入的完整验收。
Final: Ruling: 不核验远程同步状态——按用户要求本轮未commit/push，HEAD仍为6c880d9；
代价：不报告本地与远程是否同步。
原保护清单77份文件在最终复核时再次确认未变；Qwen/K256工程和位流保留。
