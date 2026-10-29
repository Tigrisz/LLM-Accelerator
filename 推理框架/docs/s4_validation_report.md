# S4 验证报告

2026-10-25。工具0.4.0；static runtime、C平台/后端回调、执行描述均为API/格式1。
原C ABI、模型包、Python平台/后端、原追踪格式仍为1。规格 static_runtime.md，实施记录 s4_plan.md。

## 完成内容

PC离线复用模型包完整检查和内存规划，导出无指针小端描述与按arena重排的权重。
C运行时验证图/存储/生命周期/地址/别名，绑定调用方arena、描述符、调用表和可选profile表，
运行时不分配堆内存。提供C平台精确读取/对齐分配/主机单调时钟/同步回调，静态整链后端回调，
未知执行/同步隔离和确认恢复，成功输出门控，独立C程序及独立版本的C追踪。

CStaticRuntimeBackend复用同一描述、同一C执行入口，绑定S3平台已有arena；
接通S2能力/选择与Session/SimDevice生命周期、原TraceRecorder及C节点CPU观测。
没有绑定具体模型、W4A8或硬件并行配置；原ir_core三份头/源码/测试未修改。

## 实测结果

- WSL Ubuntu x86_64 / GCC15.2.0 / Python3.14.4 / NumPy2.3.5。
- `IR_REQUIRE_C=1 python3 -B -m unittest discover -s tests -v`：**161/161、无跳过**，77.879秒；S4新增9项测试。
- `verify-static`：**54/54、162次**存储结果/标量Python/独立NumPy参考比较通过。
  每个样本实际启动独立C程序，子进程环境仅`PATH=/no-python`；离线导出/比较仍用Python。
- 每个样本另经CStaticRuntimeBackend+SimDevice+S3平台执行，与独立C输出逐字节相同。
- INT32/FP32各一条linear→relu→add→linear四节点链，正常输入[2,-3,4]输出[20,-25]，
  零输入输出[0,-5]，标量/NumPy/手算三方一致；普通、适配、sanitizer路径逐字节一致。
- 原生C runtime/PC平台两项可执行测试，普通和**ASan/UBSan**均通过、stderr为空；
  两类型链正常/零输入也在sanitizer独立程序中实际运行通过。
- C原生断言覆盖短读/越界/32位最后字节与4GiB拒绝、大小算术溢出、对齐/预算/分配失败、
  外来allocator、旧block覆盖/读取失败保留、未知后端/同步拒绝复用/关闭/重绑和确认恢复、
  生命周期复用冲突、前向引用、元数据容量不足、arena重叠和padding。
- Python驱动独立C负控覆盖坏CRC、CRC重算后的坏rank/count/workspace/前向引用/复用冲突/尾部数据、
  权重损坏、短输入，均在发布输出前拒绝并清理；数值早期/末期失败分别完成0/3节点，不生成输出。
- RLIMIT_FSIZE=4、忽略SIGXFSZ的真实写故障：返回IO_ERROR且清理本次部分输出。
- 适配路径追踪**3786事件**，完整且导出/回读校验通过；C追踪缺同步、缺节点、错完成数、
  错节点状态、时间反转5项负面对照均被拒绝。
- 平台受管分配/字节、文件、隔离登记均0；模拟设备task/session/staging均0；各成功C进程分配余额0。
- `ldd`确认独立host仅libm、libc与系统加载器，无Python动态依赖。
- 当前C/Python来源与构建记录指纹一致；109冻结文件、原ir_core三份文件、S3清单与369项旧证据不变。

## 独立审查

一次只读独立审查：0 Critical、3 Important、0 Minor。

1. 读取到非空block时，失败路径误释放旧资源。
2. 向已有block重复分配覆盖句柄并泄漏。
3. host写入/关闭失败后留下部分数值文件。

全部由本轮测试复现RED后，一次修复为：alloc/read拒绝非空目标且保留旧资源；
host只清理本次独占创建的失败输出。专项9/9与最终全量161/161通过。
未进行第二轮独立复审；修复有效性由作者回归和最终端到端验收支持。

## 证据与限制

- build/s4_validation_final/report.json：54样本、双链、原生测试、追踪与资源结果及构建命令/指纹。
- build/s4_validation_final/build/ir_static_host：实际独立C可执行程序（Linux x86_64）。
- build/s4_validation_final/standalone/：每个样本导出、输入/输出、C追踪和stdout/stderr。
- build/s4_validation_final/adapter_trace/：S2/S3/模拟设备集成追踪及校验清单。
- build/s4_unittest_final.log、build/s4_baseline.json、build/s4_baseline.sha256：完整回归与最终指纹。

32位仅算术范围检查，未编译/执行RV32或上板；host-coherent同步不证明DMA/cache/FENCE。
描述CRC32只检损坏，不认证来源；并发修改文件不是事务快照。
C inspect约32KiB栈临时元数据、context约20KiB固定元数据，需要后续按目标平台裁剪/预算；
MemoryPlan描述arena，PC host另计元数据，尚未完成S5整个运行时资源账本。
适配器只开放内建同线程C后端；将来开放异步C后端/平台回调前须扩展适配器C状态恢复确认。
未实现模型完整生成会话、新算子、S5/S6或真实硬件服务；未提交/推送。
