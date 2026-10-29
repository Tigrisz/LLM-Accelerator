# S3：PC 平台服务与安全边界计划

用户已授权 S3；在指定目录原地实施，不提交/推送，不改冻结输入、C ABI 或模型/量化配置。
按已批准的平台读取/对齐内存/时钟/同步方向执行，先 PC，不实施板端 C 运行时。

## 接口与实现范围

- platform.py：ReadSource/read_exact、Platform/PCPlatform；AlignedAllocator/PCAllocator/MemoryBlock；
  ClockSource/PCClock；Synchronizer/PCSynchronizer；显式 uint64 算术、offset 和 32/64 位地址范围检查。
- model_package.read_package(platform=...)：固定本地包路径通过平台精确读，限长、短读/变化拒绝；格式不变。
- runtime：平台分配共享权重/会话 arena，失败回滚；LoadedModel.close 禁止在会话仍借用时释放。
  Session.close 归还会话内存，未知执行/同步状态不释放；同步失败不切后端、不返回有效输出。
- memory.validate_plan_addressing：独立验证计划 offset/容量/size_t；32 位测试不伪造实际主机指针。
- TraceRecorder(clock=...)：主机单调 ns 时间源；不可用/倒退明确不完整，计算不受观测异常影响。
- SimDevice(platform=...)：传给会话；原 FIFO/lease/取消/恢复保持，恢复需未知服务分别确认静止。
- platform_validation.py / verify-platform：54 样本平台调用与实际 C 对齐，故障/边界探针，原 S2 全路径验收。

## 决策

- 工具 0.3.0 / 平台 API 1 / 文档 v0.3.0；后端 API 1、原有磁盘格式/C ABI 1 不变。
- 精确读遇到短读报 IO_ERROR，不补零/截断/静默成功；读取失败不返回部分模型。
- allocator 预算覆盖受管 backing（包括 alignment-1），不等于 RSS；不保存强块引用阻止旧 API 的正常 GC。
  PC 默认分配预算 64MiB，可显式配置；模型预算与分配器预算都必须满足。
- 显式 close + Python GC 兼容；借用期间 close 模型报 BUSY，不释放在途 arena。
- PC 同步只表示本进程 host coherent，无 DMA/cache/硬件 FENCE 保证；同步未知时隔离，确认后恢复。
- 文件偏移按 uint64；目标地址检查与实际 host pointer 分开，禁止取低 32 位模拟移植成功。
- trace 默认 perf_counter 域不变，自定义 host_monotonic 域单列；CPU ticks/逻辑 tick 不混合。
- S1/S2 清单与旧证据保留历史快照，新增 S3 独立证据。

## 验收任务

- [x] 1. 原语 RED -> GREEN：短读/越界/溢出/非法类型、对齐/预算/失败/释放、32 位最后一字节/边界。
- [x] 2. 模型/内存/后端集成 RED -> GREEN：失败清理、共享权重借用、无隐式回退、原数值不变。
- [x] 3. 时钟/同步/模拟设备 RED -> GREEN：坏时钟不改变计算，同步失败保留资源/输出无效，恢复需确认。
- [x] 4. 54/54、162 比较及 S2/A7/C sanitizer；完整152/152无跳过；冻结文件/C 和旧证据不变。
- [x] 5. 一次独立只读审查，3类问题一遍修复，25项平台专项及最终全量通过；版本/文档/最终指纹固化。

Final ruling：正常对象保留旧 GC 兼容；未知执行/同步与未完成关闭转入可枚举的进程级强保留，
只有确认/清理成功才解除，防止整个对象图被循环 GC 收走。
关闭开始与 binding 已关闭分开标记；同步证据必须匹配所属 run 完整上下文。

Review focus：零长与整型溢出、allocator 部分失败泄漏、模型过早关闭/GC兼容、未知同步资源提前释放、
时钟异常非干扰/倒退、目标32位与真实PC地址混淆、prepare/close失败的回滚、数据可见性未确认却返回输出。
执行记录 docs/progress.md，证据 build/s3_*；不操作上层其他项目。
