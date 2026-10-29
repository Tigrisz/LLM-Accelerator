# A5 最小模型包和运行时内存规划实施计划

日期：2026-10-24。依据：用户本轮明确授权 A5；延续 A1—A4 已批准路线。
执行：writing-plans、executing-plans、test-driven-development；最终独立只读审查。

## 目标与范围

实现模型无关的 model-package-v1、严格加载/检查、确定性内存规划及 PC 会话，
执行现有 linear（可选 bias）、add、relu 和 FP32/INT32，不引入模型、量化或硬件依赖。
JSON 由 Python 加载；数值计算全部通过 A4 C ABI。不是板端 C 包解析器。

Ruling：用户明确要求直接续做 A5，按已批准架构收敛实现细节，继续执行不另设审批。
Ruling：沿用指定目录及 docs/progress.md，不创建 worktree/提交、不改其他项目。
Ruling：采用 JSON+固定 weights.bin 而非引入 ONNX/任意代码插件；可扩展版本，
代价是当前仅支持明确声明的静态顺序 DAG，模型适配器需后续实现。

## 文件与接口

- inference_ref/model_package.py：不可变包记录、write_package / read_package、严格文件和图检查。
- inference_ref/memory.py：plan_memory(package, memory_budget=64MiB, alignment=64) -> MemoryPlan。
- inference_ref/runtime.py：inspect_model / load_model / create_session；预分配 arena 并绑定 C 描述符。
- inference_ref/package_validation.py：既有 54 样本包装后真正加载/执行/三方对齐，双类型四节点链。
- inference_ref/__main__.py：inspect-model、verify-packages 入口；原入口保持兼容。
- tests/test_model_package.py、test_memory.py、test_runtime.py：先 RED 后 GREEN。
- docs/model_package.md、a5_validation_report.md，更新 README/contracts/progress。

## 契约

固定 manifest.json + weights.bin；版本/字段/重复 JSON 键、ID、角色、图引用、类型/形状、
字节序、偏移/长度/非重叠/64 字节文件对齐、整体与分段 SHA256 均检查。
限制：清单 1MiB、权重 16MiB、4096 张量、1024 节点、原单张量 1048576 元素；
默认总受管 arena 64MiB，可显式降低。预算不是 Python/进程总内存承诺。
固定支持集之外返回 UNSUPPORTED；禁止隐式转换、广播及包中代码执行。

图预先按拓扑顺序排列；单次赋值；常量/输入只读；中间/输出恰好一个生产者。
模型输入输出由清单声明；不包含 expected，不预填最终答案。

三个 arena：共享只读权重、每会话激活、每会话共享 scratch；先规划和预算检查再申请。
非 padding 激活使用闭区间生命周期 first-fit 槽复用；同节点读/写不能重叠。
最终输出保留到链尾；padding 张量使用独立槽；每次运行先清零激活再复制输入。
单次执行期间不为每节点重新分配张量/工作区；输入检查和返回复制不计入 arena 预算。
失败不返回有效输出，记录 C 状态/完成步数；下次完整 run 可以重试。
会话只支持同步执行，无 KV、token、prefill/step、异步设备和动态形状。

## 任务及验收

- [x] 任务 1：包格式。先测试缺失功能，再实现读写/图校验/损坏和越界拒绝；纯 Python 回归通过。
- [x] 任务 2：内存。消费不可变包，产生不可变 plan；先测试预算/复用/输出保留/padding，
  再实现；枚举存活张量检查区间不冲突，预算少 1 字节必须失败。
- [x] 任务 3：运行时。消费包/plan/CBackend，直接在 arena 上绑定 CTensor/CCall，
  真实 C 调用；先测试端到端、重复运行、会话隔离、失败重试、关闭生命周期，再实现。
- [x] 任务 4：验收入口和文档。54 个原样本 -> 包 -> 加载 -> 规划 -> C 执行，
  对齐 stored/scalar/NumPy 共 162 项；FP32/INT32 多节点链对齐并报告内存复用。
- [x] 任务 5：完整 A1—A5 测试、A4 原生 sanitizer、冻结文件/源码哈希、独立审查及最终复验。

Pre-flight：包记录是规划器唯一输入；plan 偏移/长度是 runtime 唯一布局来源；
runtime 不用 A4 Tensor/Call 的独立分配器，直接共享 C ABI；scratch 与全部张量分离。
闭区间保证 A4 禁止同节点 input/output 别名；padding 独立槽保证 A4 零 padding 语义。
所有任务执行与偏离在 docs/progress.md 记录，最终证据写入新 build/a5_* 目录。

最终：71/71 测试无跳过；54/54 包、162 比较、两条四节点链、原生 C sanitizer 通过。
独立审查发现的 1 项路径错误类型 Minor 经回归 RED -> GREEN 修复。
证据 build/a5_validation_final/report.json、build/a5_unittest_final.log。
