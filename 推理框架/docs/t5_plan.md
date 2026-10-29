# T5：现有INT32样本迁移到RV32

2026-10-26，用户授权先同步能力文档，再迁移现有INT32样本，同形状/数据对照Python、PC C、RV32单/双发射，重复运行及异常路径。容量不足明确标记，不绑定模型/W4A8。

- [x] 同步S6能力/差距/接入说明与T4当前证据；明确旧PC验证、T4合成链、T5范围和实板未知。
- [x] 枚举54个冻结样本并固定109文件哈希；INT32共27，FP32共27明确不在本轮目标迁移范围。
- [x] 同包导出、PC独立C基准和双Python参考；一例一固件，原输入/零输入/原输入、恢复后原输入、close/rebind后原输入，真实UART输出逐字节比较，不向正向固件嵌入golden。
- [x] 实际ELF/map检查TCM和栈边界；明确blocked_tcm vs编译工具错误，另以真正超大静态段负控证明容量门禁，不改变原样本。
- [x] RV32单/双配置异常：短镜像/CRC/检查区/容量/arena/32位范围，缺输入/错误长度/重复run/无效输出，同步未知/拒绝关闭/拒绝恢复/恢复后执行、关闭重新绑定；另合成数值溢出探针，不冒充冻结样本。
- [x] 新门禁测试RED→GREEN；一次独立只读审查，必要修复后当前PC与RV32源副本最终验收、历史收据/来源/样本/新证据指纹封存。

Ruling: 原地实现，不修改原C核心/运行时/冻结样本/上游RTL/T4旧证据。沿用T4已核对的xPack工具链与portable-metadata兼容RTL，明确选择身份及未上游合入；本轮不扩FP32目标执行、实板、DMA/OS或新模型。

Ruling: 一例一固件而非把全部样本打成一个大镜像，保留每个真实shape/storage/payload并记录每例ELF/map。所有容量判断基于实际链接结果和受测64KiB TCM/8KiB栈预留；这不是板端可用预算。检查无分配器符号、ABI/ISA及实际sp；观察高水位不代表最坏栈。

Ruling: 重复输入零化仅为额外输入场景，原输入必须先后真实运行并对齐；不缩小维度，不把容量阻断计为数值通过。总体报告分别给已执行通过、blocked_tcm、failed、unproven及覆盖完整性。

## 执行记录

- 离线初轮在PC build_backend返回Path的调用适配处工具层失败，保留build/t5_pre_review/failure.json；按现有API修复，不作为RV32或C算术缺陷。新目录t5_pre_review_v2实际27/27通过、TCM阻断0、双配置5次有效输出、溢出/超容量探针通过。
- 新增保真校验，逐tensor逻辑/物理shape/dtype/layout和物理input/weight SHA与冻结样本核对；拒绝改shape/改feed的回归RED→GREEN。加异常进程退出容量误判反例RED→GREEN。专项初验5/5。
- 一次独立只读审查0 Critical/2 Important/0 Minor。审查重新解析全部54份初验实际stdout通过。发现缺失样本可虚高覆盖、混合链接错误可冒充容量阻断；新增完整suite/缺根/缺例/改索引/改manifest和混合错误反例RED→GREEN，专项现6/6。
- 修复前工具编译即严格核验固定suite SHA、54例/109文件集合、manifest/payload SHA、27 INT32/27 FP32；只接受全部诊断均为已知容量类的链接阻断。未知/混合错误归tool_error。源与fixture输出位置强制分离。
- 审查Declined项（最终源副本/历史证据/实板/FP32/最坏栈/ISR/DDR等）由实施者实际验收或继续未知；不二次独立复审。准备最终PC/目标干净副本回归及新指纹。
- Final: 审查修复后PC源副本174+50项无跳过、54样本/双类型链/24压力/200轮/原生及sanitizer通过；目标源副本27/27 INT32全部通过、TCM阻断0、54个profile/270份有效输出、13组检查及溢出/真实容量负控通过。两副本各312文件，初始无build，运行前后源与副本指纹一致。
- Final: 实测初始化镜像30808—31288字节、最高BSS末32480、样本观察栈816，两配置一致且无trap/越界；均不是最坏栈或板端实际预算。FP32目标、实板等仍未知，不绑定模型/W4A8。
- Final: 封存build/t5_finalize.py，新汇总build/t5_validation_final/report.json，新基线build/t5_baseline.json/.sha256；原核心/旧基线/109输入保持，三份晚于运行的收尾文档单列。无延期，不二次复审，不提交推送。
