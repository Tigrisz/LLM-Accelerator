# S2 验证报告

2026-10-24；工具 0.2.0、Python 后端 API 1；规格 backends.md，计划 s2_plan.md。

## 已实现

通用 StaticBackend/BoundChain 与不可变需求/能力报告；旧 CBackend 自动适配。
会话创建前整链能力选择，默认禁止回退，只在明确不支持且策略显式允许时尝试后备。
配置/查询/绑定/执行失败不触发重选；保留静态 MemoryPlan/arena 和原数值语义。
模拟设备与实际执行解耦；异常状态不复用/关闭同步会话，后端拒绝恢复时保留 task lease。
backend.selection 与实际后端关联，C/generic 事件和时钟分离，旧日志仍可读。

## 证据与过程

- 初始 7 项后端测试因缺实现 RED，抽离 C 绑定后 GREEN。
- generic 事件误按 C 校验、篡改后端 ID 未拒绝，均先 RED 再补一致性检查。
- 同步未知状态可提前复用、只读输出误支持，先 RED 后修复；恢复必须明确确认。
- 未知执行状态曾沿用 INVALID_ARGUMENT 占位，新增回归先复现，再明确记录 DEVICE_ERROR。
- 新 verify-backends CLI 先因无入口失败，再实现 54 样本/显式回退/实际 C 验收。
- 审查前完整 125/125 无跳过；S2 专项 18 项，包含真实 C 和独立于 C 接口的测试后端。
- build/s2_validation_pre_review/report.json：54/54、54 次显式回退、162 比较，实际后端 pc_c；
  主追踪 4378 事件，原运行时追踪 3046 事件，完整且回读通过。
- 原双类型链、8 生命周期场景、2 观察故障探针、8 语义负面对照和 C ASan/UBSan 通过。
- 主验收设备 live_tasks/live_sessions/staging 均归零；故意拒绝恢复时 lease 保留，确认后归零。

pre_review 为历史过程，不作为后续修复的最终指纹。

## 独立审查与修复

一次新上下文只读审查：0 Critical、2 Important、0 Minor。
作者独立复现后在一次修复中处理：

1. generic 已确认 DEVICE_ERROR 可能出现在节点之间或全部节点成功后；旧校验误套 C 失败节点规则。
   新增实际 C 前缀执行 2/4 节点后返回 generic 设备错误的回归，均先 RED；修复后通过。
2. 删除 session.open.selected_backend 可跳过该会话全部后端身份校验。
   字段删除 + chain 身份篡改负面对照先 RED；改为根据 S2 selection/元数据强制身份关联后通过。

两项身份负面对照同时写入正式 CLI 报告，重算事件字节计数后仍必须失败。
未追加第二轮独立审查；修复是否生效由上述 RED -> GREEN 回归及最终完整套件验证。
审查另确认恢复再次抛异常时不解封同步会话、close 异常时模拟会话保持注册，可明确重试；
没有独立重跑全量或 sanitizer，该部分属于下述作者实际验证。

## 最终结果

- 完整 **127/127**，无跳过；S2 **20 项**，保留原 S1 107 项。
- 环境 WSL Ubuntu x86_64、Python 3.14.4、NumPy 2.3.5、GCC 15.2.0，IR_REQUIRE_C=1。
- **54/54** 样本直接 C/显式回退 C 逐字节相同，**162** 项参考比较通过，**54** 次明确回退选定 pc_c。
- 主 trace **4378** 事件，原 runtime_trace **3046** 事件，均完整、无丢失/采集错误，导出回读通过。
- 两种 S2 选择身份负面对照均被拒绝；嵌套 A7 八种负控、两条四节点链、八生命周期场景、
  两观察故障探针及实际 C ASan/UBSan 通过，native stderr 为空。
- 主验收两设备 live_tasks/live_sessions/staging 全部归零；拒绝恢复时资源仍受保护。
- 109 冻结输入、全部 c/ 源码与测试、S1 封存清单及其全部证据不变。
- Python 源码、C 源码/原生测试、编译库/原生测试二进制与报告指纹已核对。

最终证据：build/s2_validation_final/report.json、build/s2_unittest_final.log。
正式目录的 trace/ 是选择/回退证据；runtime_trace/report.json 与其子目录是原 A7 全路径证据。
build/s2_baseline.json / s2_baseline.sha256 固化本次版本、当前源码/文档/测试、冻结输入和证据指纹；
S1 清单保留为历史快照，不要求新增 S2 源码匹配旧快照。

复现命令（本目录 WSL/Linux；输出必须换新名称）：

    IR_REQUIRE_C=1 python3 -B -m unittest discover -s tests -v
    python3 -B -m inference_ref verify-backends --fixtures fixtures/synthetic-v1 --output build/s2_run_new

## 范围与限制

测试用 test_denied 只明确拒绝能力，不能进入 prepare，不是硬件后端。
54 数值对照均由实际 PC C 运行；非 C 测试后端验证替换接口，不作为生产软件回退。
后端为受信进程内对象；框架验证结构/状态/关联，不能证明任意插件数学正确或隔离恶意指针。
尚无自动异构切图、S3 平台服务、板端 C 运行时、真实模型/量化或 RV32/FPGA/硬件性能验收。
工具/后端 API 版本与磁盘/C ABI 分开；S1 封存清单不改写，本轮未提交/推送。
