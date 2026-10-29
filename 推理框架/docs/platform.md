# S3：模型无关平台服务（PC 实现）

工具0.6.0、平台/后端API1、文档契约v0.6.0；原磁盘格式/ir_core ABI1不变。T3纯C native ABI2及显式元数据见t3_metadata.md；C PC结构ABI2见resources.md，S4见static_runtime.md。
当前 Python/NumPy PC 运行时通过平台服务读取模型包、分配 arena、取得主机时间并同步可见性。
不绑定模型、W4A8 或硬件参数；不是板端 C 平台层、DMA/cache 驱动或 RV32 执行证明。

## 接口

| 接口 | 契约 |
| --- | --- |
| ReadSource.size / read_at(offset,length) / close | uint64 字节大小与偏移；随机读可返回短读，调用方必须检查；支持 with |
| read_exact(source,offset,length) | 先查范围；只接受精确长度 bytes，短读/错误类型报 IO_ERROR，读缓冲 MemoryError 报 RESOURCE_LIMIT；不补零或静默截断 |
| Platform.open_read(path) / read_blob(path,limit,trace=None) | read_blob 固定一次 size 快照并限长，精确读，成功/失败均关闭；PC 来源仅普通非符号链接文件 |
| AlignedAllocator.allocate(size,alignment) / release(block) / stats | 申请前查大小/预算/size_t，成功取得一个所有权块；分配失败不取得所有权、不计费 |
| MemoryBlock.data/backing/address/close | host NumPy 字节块；data 对齐、backing 含额外空间；close 幂等，外部分配器 release/重复 release 不合法 |
| ClockSource.now_ns() | host 单调非负 ns 或 None；源的 domain/unit 显式声明，不把设备 tick 当 ns |
| Synchronizer.for_device(blocks) / for_cpu(blocks) | 同步完成与可见性确认必须返回 True；False/异常表示未知，不允许返回有效输出 |
| Synchronizer.recover() | 真实确认不再访问借用内存才返回 True，默认 False |
| PCPlatform(allocator=None,clock=None,synchronizer=None) | 显式组合服务，无全局隐藏配置；PCPlatform.stats 为受管 backing 与打开文件计数 |
| retained_resources(platform_id=None) | 枚举异常强隔离记录（retention_id/platform_id/reason/owner），owner 可明确 recover/close；不提供强制释放 |

Platform API 是进程内受信对象接口，不从磁盘包加载可执行代码，不隔离恶意实现。
当前 allocator 提供 host NumPy backing；运行时仍在 Python 中创建视图，C 算术通过既有 ABI 执行。
PCFileSource 用打开文件大小检查范围与读取期间的大小变化；SHA256 继续验证内容。
这不是并发编辑文件的事务快照，同大小并发改写不在保证范围内。

## 接入方式

    platform = PCPlatform()
    trace = TraceRecorder(clock=platform.clock)
    model = load_model(package_path, platform=platform, trace=trace)
    with create_session(model, c_backend) as session:
        outputs = session.run(feeds)
    model.close()

导入 inference_ref.platform 中的 PCPlatform，及原 runtime/tracing API。
read_package/inspect_model/load_model 支持 platform；create_session 与 SimDevice 也支持 platform。
未显式指定时，会话继承 model.platform，模拟设备默认允许按模型继承；旧调用仍可使用。
同一个 PCPlatform 可共享给多个模型/会话；其 allocator 预算是这些受管块的合计。
S2 的 registry/policy 仍可使用，平台错误不触发后端重选或数值回退。

## 内存与生命周期

PCAllocator 默认 budget_bytes=64MiB，可配置；alignment 为 4..4096 的 2 次幂。
每非空 backing 为 size+alignment-1，空块 backing=0/address=0；与原 MemoryPlan 预算一致。
模型预算检查与平台 allocator 预算都必须通过，平台合计预算可能先拒绝额外会话。
这是实际受管 backing 额度，不包含包 bytes、Python 对象、输出副本、描述符/profile/trace 或 RSS。
不声称实现 S5 的所有资源账本/全进程全局内存上限。

分配失败回滚已成功取得的会话块；模型权重不因会话分配失败而释放。
LoadedModel.close 在任一会话仍借用时返回 BUSY，关闭后不可创建新会话。
Session.close 在任何关闭动作前锁定，先关闭 binding，再清理视图并释放会话块；
binding 或部分释放失败均可明确重试，不能重新 run，未确认关闭的 binding 必须重试而不能跳过。
模型/块 close 幂等。所有外部借用视图在释放后失效，即使 NumPy 引用可能延长底层物理存活。
为兼容旧调用，allocator 不以强块引用阻止正常 GC，模型用弱会话登记；正常旧对象 GC 不造成永久借用。
未知后端/同步状态与未完成关闭会转入进程级强隔离登记，不能通过丢弃整个
session/model/platform 对象图绕过保护。此登记是安全保留，不是隐藏平台配置，可能持续占用资源。
可用 retained_resources() 找回 record.owner；通过 owner.platform 获取对应服务并执行真实恢复确认，
或对 close_incomplete 明确重试 owner.close。没有确认的记录不会因 GC 自动释放。
recover 成功（且未处于关闭流程）或 close 全部清理成功后才撤销登记；stats 中 retained_resources 应归零。
显式 close 才有确定的释放时机/追踪；GC 释放不作为完整 RSS 或释放事件统计。
会话和模型仍须串行使用；局部服务锁不等于可并发运行的模型调度器。

## 地址与溢出

- checked_mul：uint64 乘法检查，拒绝 bool、负数与溢出。
- checked_range(offset,length,capacity)：uint64 文件/缓冲区范围，先减后比较，不截断。
- checked_span(address,length,bits=32/64)：检查地址与 size_t，最后一个字节 0xffffffff 长度 1 合法；
  数学上的 exclusive end=2**32 不是可转换指针。base=2**32、跨边界或不可表示 length 均拒绝。
- validate_plan_addressing(plan,address_bits=32/64)：检查 arena、placement offset/容量与总 backing 的可表示性。
- allocator 验证真实 PC backing 和对齐后数据地址；pointer_bits=32 时不能把高位 PC 地址取低 32 位。

文件偏移、主机指针、目标地址检查是不同语义。32 位探针只验证范围与拒绝行为；
不生成虚构的可解引用目标指针，不代表 RV32 交叉编译、仿真或实板通过。

## 时间与同步

PCClock 使用 perf_counter_ns；TraceRecorder(clock=...) 默认仍是 host_perf_counter 域。
可注入 host_monotonic/ns 源；snapshot、主机跨度、摘要/时间线均保留对应域。
不可用、异常、倒退或非法样本会明确标记 trace 不完整，不伪造时间、不改变计算结果。
C clock() CPU ticks 与模拟逻辑 tick 保持独立，时间分辨率不等于 1ns。

PCSynchronizer 只确认同进程 host coherent，semantics=same_process_host_coherent_no_dma。
它检查借用块仍有效；不操作或证明 DMA/cache clean/invalidate、总线同步或硬件 FENCE。
顺序为：输入准备 -> for_device -> 整链执行 -> for_cpu -> 复制有效输出。
输入同步失败不进入后端；输出同步失败保留已完成 C 节点数，输出无效。
同步异常会隔离会话/模拟任务，保留 arena/lease/staging；需要对应未知服务确认后才能恢复。
如果后端执行也未知，后端确认不能替代同步服务确认。默认 PC 服务没有后台访问，故可确认静止。

## 追踪与验收

新增 platform.read/allocate/release、platform.sync.to_backend/to_cpu 及读取/分配结果元数据。
session.open 含 platform_api/platform_id/pointer_bits，run/sync 关联相同平台。
同步事件还必须与所属 run 的 model/session/task/device/selected_backend 完整上下文一致。
S3 成功运行必须具备有序的输入发布、整链、输出可见性同步及输出阶段；删去同步记录会验收失败。
旧 S1/S2 日志仍可读，旧格式未新增必需的磁盘字段；S3 语义应使用当前工具校验。

本目录 WSL/Linux，输出换一个不存在的新目录：

    IR_REQUIRE_C=1 python3 -B -m unittest discover -s tests -v
    python3 -B -m inference_ref verify-platform --fixtures fixtures/synthetic-v1 --output build/s3_run_new

verify-platform 报告 inference-platform-report/version=1，验证 54 样本/162 比较，平台资源归零，
短读、uint64/目标32位、部分分配失败、坏时钟和同步隔离/恢复探针，以及缺少输出同步的负面对照。
backends/ 另运行原 S2/A7 路径、逐字节回退对照、生命周期/追踪负控与实际 C ASan/UBSan。
CLI 0/1/2 分别表示通过/验收不通过/参数或工具或 I/O/输出冲突。
当前结果和限制见 s3_validation_report.md；所有结论只对应 PC 静态支持范围。
最终152/152无跳过；正式证据 build/s3_validation_final/report.json 与 build/s3_unittest_final.log。
build/s3_baseline.json / s3_baseline.sha256 是当前版本/内容/证据收据，不是认证签名或 Git 发布。
