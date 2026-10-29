# T2 验证记录

日期2026-10-25，运行时0.5.0，T2资料/核对工具v1。

已取回并核对固定主仓库c1bc715b276db48cf6e6b640701d51b72e984d77的27份源文件，Git blob匹配；核对赛题PDF17页与板卡手册61页，相关页提取保留并记录原PDF SHA256，指南PDF11/手册PDF24渲染目视核对。
形成54约束、43来源，source_confirmed30、normative2、derived3、historical_report3、proposed3、unknown13；9领域齐全，6类目标预算为null，target_ready/target_execution_verified=false，model/quantization=null。

当前Windows/默认WSL PATH无具名交叉GCC；WSL具名dpkg包不存在，有限/opt、/usr/local搜索未找到。未遍历全磁盘或安装工具；不是全部主机/发行版都不存在的结论。
WSL Ubuntu26.04.1/readelf2.46/Verilator5.032可见，非目标编译或RTL结果；本机无D:\FPGA\RiscV历史路径，使用固定远程快照。
关键结果：64KiB共享TCM、最小8KiB栈预留，实际预算未知；1GiB物理DDR未映射；32KiB检查器局部数组及20KiB context数组为推导，未测目标sizeof/高水位；无FPU，C参考路径的binary64/fenv/profile clock依赖待验证。

## 验证过程

- 初始Windows测试临时目录被沙箱拒绝创建（WinError5），不是功能RED；改用已有WSL运行，不降低断言。
- WSL负控真实复现4个FAIL：删除单项、unknown提升确认、TCM容量篡改、栈工作集篡改未被初版门禁拒绝；补54身份/13未知/关键推导约束后回归。
- 预审工具19/19通过（原T1工具14+T2新增5），无跳过；结果build/t2_tools_pre_review/result.json。
- 一次独立只读审查：0 Critical / 1 Important / 0 Minor；当前事实与原PDF/源码一致，指出来源集合/blob字段/提交身份未强制检查。
- 新增6分支回归：删除来源、移除27份blob字段、改目标提交、改索引提交并更新其SHA、改来源ref、改路径；前5分支实际FAIL，路径分支已有哈希门禁拒绝。
- 一次修复固定43来源身份与路径，27份blob/ref/URL必需，仓库/提交与repository索引逐项一致。中间完整20项出现1个ERROR：GitHub中文URL已百分号编码；按规范编码比对修正后继续同一修复批次。
- 最终工具20/20通过（原T1工具14+T2新增6），无跳过、失败或错误，证据build/t2_tools_final_v2/result.json；未进行第二轮独立复审。
- Windows最终离线核对通过：build/t2_evidence/audit_windows_final.json；最终WSL/干净副本与收据见下文。

## 最终结果

- build/t2_clean_final_v2：新259输入快照，启动时无build/.git、不复制历史构建；在T1固定环境策略下运行T2审计和只读环境探测，退出0、stderr空、passed=true，受测时原源与副本集合/指纹一致。
- 首次最终副本编排把capture_output传给Popen封装，审计未执行即TypeError；没有计为通过。改用PIPE并新建v2副本后成功，未修改T1工具。早期副本与失败尝试保留。
- 原55份runtime/C/tests、109冻结输入、全部170份T1受测代码/输入（还含既有工具）与旧指纹一致；既有项目文件仅README/progress变动。S1—T1收据及各自证据指纹全部复核通过，两份原PDF哈希与选页重新提取一致。
- 最终副本之后仅plan/report/progress收尾；代码/数据/来源仍与受测快照一致，差异和全部当前文件指纹列入本轮收据。
- 汇总build/t2_validation_final/report.json，完整性build/t2_final_integrity.json，收据build/t2_baseline.json及t2_baseline.sha256；收据为本地可复核指纹，不是认证或Git发布。

T2已完成目标约束核对范围；独立审查1项Important经反例回归修正，未独立复审，无延期Minor。下一步先确认工具包并处理32KiB检查器工作集/目标map和栈，再进入目标平台适配。

## 验证边界

本轮验证资料、源码、快照与只读环境探测，未交叉编译/链接、未运行RV32/RTL/PDS/实板、未下载位流；无DDR/cache/DMA或真实模型验证。
原174项、54样本/双链和压力最近完整新构建是T1，不把它说成本轮重跑；本次未改原runtime/C/tests/109冻结输入。
核对工具passed仅表示证据门禁通过，未知保持未知；未提交/推送。
