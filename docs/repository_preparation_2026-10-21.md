# UART实板验证完成后的提交整理

## 本次整理范围

保留当前PDS工程、源码、约束、.mem、最终UART位流及LED-only回退位流，
保留验证报告与三次真实板端数据。没有修改计算功能，也没有执行commit/push。

| 目录 | 提交内容 |
| --- | --- |
| rtl、model、tests、scripts、constraints | 源码、验证脚本和约束 |
| fpgatest/qwen_slice/prj | prj.pds、source、mem、两个最终.sbit |
| docs | 协议、实板验证、任务A交接及本说明 |
| evidence/uart_board/2026-10-21 | 三次bin/JSON、manifest、下载日志、切片配置和量化尺度 |
| evidence/pds/2026-10-21 | 当前PDS工具报告与各阶段完成日志快照 |
| evidence/rtl/2026-10-21 | RTL回归结果及独立整数黄金值检查快照 |
| deliveries | 给任务A的固定ZIP及SHA256 |

build、artifacts、tmp、虚拟环境、Python缓存和PDS中间产物继续留在电脑上，
不纳入新提交。新增.gitignore规则，并从Git索引移除历史已跟踪的PDS生成目录，
只停止跟踪、不删除磁盘文件；缺少的旧生成文件原本就由PDS重建/替换，未恢复旧缓存。
因此git status中会有一批已暂存D，这是清理版本管理，不是删除当前工程源码。
其他源码/文档改动保持未暂存，由用户统一审核与git add。

.gitattributes为evidence、deliveries和.sbit禁用行尾转换，保证原始证据字节和SHA256
在Windows/Linux克隆后仍可比对。副本和交付包均核验不变，原artifacts不删除。
PDS活动缓存不重命名、不搬走；打开的工程无需关闭。

## 整理后的验证

提交前核验归档与原始文件逐字节一致、三个bin/JSON/manifest逐项一致、位流和.mem
校验值一致、交付ZIP的内部SHA256及CRC正确，并检查PDS输入源/约束路径仍存在。
本次整理不重新声称执行PDS全流程或重新物理复位；原实测证据日期见各报告。
独立整数黄金值报告重新针对当前PDS.mem生成，确认N16/K2048、256项一致；
没有沿用被N3/K256单元测试夹具覆盖的旧build/reports/board_mem.json。

## 用户自行提交

在仓库根目录先检查清单与缓存移除，再暂存并复查：

```bash
cd /mnt/d/GPT/qiansai_FPGA
git status --short
git add -A
git diff --cached --stat
git diff --cached --name-only
```

确认没有新增虚拟环境、构建数据库、PDS自动备份或临时日志；当前源码、约束、
最终.sbit、evidence与deliveries都应在提交范围。看见旧缓存的删除记录是预期行为。

```bash
git commit -m "Add validated Qwen UART readback and archive board evidence"
```

如仍使用SSH拉取/推送，可用SSH地址同步远程，避免改动现有origin配置：

```bash
git fetch git@github.com:Tigrisz/LLM-Accelerator.git main
git log --oneline --left-right HEAD...FETCH_HEAD
git merge FETCH_HEAD
```

若merge报告冲突，解决后再提交合并；不要直接强推或覆盖远程。
若合并改变了源码/工程配置，应重跑相关RTL回归；原位流和板端报告只证明原快照，
不能自动给合并后的新RTL背书。

```bash
git push git@github.com:Tigrisz/LLM-Accelerator.git main
```

当前origin仍配置为HTTPS，本次整理不改远程、不fetch、不merge、不push；
上面是供用户确认提交后执行的步骤。WSL之外也可在Git Bash进入
`/d/GPT/qiansai_FPGA`后使用同样Git命令。
