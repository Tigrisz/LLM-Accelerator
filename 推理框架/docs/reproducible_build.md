# T1 干净副本构建与验收（工具v1）

T8新增当前版本PC+RV32总入口：`tools/reproduce_total.py`，同一干净副本运行54原样本/两原链、两种发射配置与异常/容量负控，命令和状态见[t8_validation_report.md](t8_validation_report.md)。下述T1入口继续作为PC专用全量入口，历史结果不回写。

当前运行时0.6.0，T3 native ABI2；T1历史受测版本0.5.0。原174项Python测试和冻结样本保持。
不需要历史build、Git元数据、网络、具体模型或W4A8；需要预先具备的PC工具环境。

## 唯一推荐入口

WSL/Linux，在推理框架目录执行；输出目录必须不存在：

```text
python3 -B tools/reproduce.py --output build/t1_run --iterations 200
```

Windows PowerShell可调用：

```powershell
wsl.exe --cd 'D:\GPT\qiansai_FPGA\推理框架' --exec python3 -B tools/reproduce.py --output build/t1_run --iterations 200
```

前置条件：Python>=3.10、已安装NumPy>=1.24、PATH中有gcc、cc、nm，支持C11、-fstack-usage及ASan/UBSan的Linux工具链。
当前验证环境是WSL Ubuntu x86_64；完整验收要求POSIX文件大小故障注入，不宣称Windows原生验收。
不自动安装依赖；缺工具、编译失败、超时、失败或跳过均不能算通过。
最低版本不是所有组合都已验证；报告记录实际Python/NumPy/OS/架构/编译器版本和路径。

## 执行过程

1. 工具预检，不把缺gcc的测试静默跳过。
2. 复制README/requirements/.gitignore和inference_ref、c、tests、fixtures、docs、templates、tools。
   不复制build、.git、.venv、__pycache__或共享库/对象/可执行产物；冻结fixture的.bin是必要输入数据。
   符号链接/非普通文件拒绝。源/副本逐文件哈希及完整文件集合一致性核对。
3. 干净副本为output/workspace，初始没有build或.git。子进程只在副本内创建空build。
   子进程环境只继承PATH/HOME/USER/LOGNAME；固定locale/hashseed/线程数，IR_REQUIRE_C=1且禁止pyc。
   不继承CPATH/LIBRARY_PATH/GCC_EXEC_PREFIX/LD_AUDIT等外部编译/链接覆盖；固定ASan泄漏检测及halt-on-error、UBSan halt-on-error。
4. 执行原174项：不只比较数量，还核对固定测试ID与tests源文件指纹；新增工具测试独立执行/报告。
5. 执行verify-resources，内部从C源码构建普通/sanitizer库与程序，验证54样本、双类型四节点链、24压力探针。
6. tools/audit_intake.py显式使用步骤5**本次**的static报告与新库，复验S6能力/模板/数值/布局。
   不读取build/s5_validation_final、旧收据或历史库。保留旧S6审计只作历史证据。
7. T3新增PC元数据/单函数frame对比，以及T2历史约束来源审计；旧框架源快照作为源码资料复制，不读取历史build，不把PC frame当目标峰值。
8. 核对实际inference_ref导入来自副本、源与副本未被修改，收集源码/构建命令/日志/二进制/结果指纹。

--iterations默认200；降低参数只降低正式资源压力轮数，结果中保留实际轮数，不能对外宣称已跑200轮。
既有174项内部也含自己的端到端小轮数测试，不代替步骤5的显式压力验收。

## 结果与复现

```text
output/source-manifest.json                 # 输入文件与内容指纹
output/workspace/                           # 可单独复制的源码，含本次新build
output/workspace/build/acceptance/
    framework_tests/result.json, unittest.log # 原174项精确ID/结果
    tool_tests/result.json, unittest.log      # 新工具测试，独立计数
    resources/report.json                    # 压力；其static_runtime中有构建/普通及sanitizer产物
    intake_audit/report.json                 # 无历史依赖的S6审计
    static_metadata/report.json              # T3 PC sizeof/编译frame；目标布局/峰值null
    target_constraints.json                  # T2历史来源核对，未知不提升
    report.json                              # 子进程验收汇总/失败原因
output/acceptance.log
output/report.json, report.sha256             # 总结果、环境、命令、所有产物SHA256
```

总入口成功exit0；验收失败exit1；工具/配置/控制器异常exit2。只有顶层passed=true且child_exit_code=0才能认定完成。
不能只看某个子报告的passed字段；汇总核查测试身份/无跳过、逐项参考比较、两类型/输入链及六种原生普通/sanitizer组合。
还核对24个固定压力身份、请求轮数/实际任务数、40个失败点、恢复/关闭与归零；独立读取C stdout/stderr/trace与输入输出文件。
特别要求普通及sanitizer执行stderr为空：UBSan可能退出0但报告错误，不能仅凭返回码通过。
控制器和各验收阶段在独立进程组执行；超时/终止时逐级清理组内后代进程，再返回失败，避免后台继续写产物。
输出拒绝覆盖；失败保留本次新产物和诊断，不删除既有目录或改写历史验收。
环境清单记录实际允许的子进程变量及编译器driver版本/路径/SHA256；这不是整个系统工具链或容器镜像的指纹。

将workspace中的源码目录带到新位置时，应排除其build，再运行同一入口；解释器/NumPy/编译器属于显式外部工具依赖。
同源码可重建并验证相同数值/状态/资源语义；时间戳、绝对路径、运行时间与部分二进制可能不同。
本工具不承诺跨环境可执行文件逐字节相同，也不声称构建了独立操作系统容器。

## 版本维护

tools/framework-tests-v1.json固定原174个ID与测试源码指纹；修改原测试须明确更新基线并审查，不能静默改计数。
T1工具测试在tools/tests，原tests目录保持不变。工具格式v1与运行时ABI/模型包格式独立。
历史S1—S6文档中的build路径是过去验收位置；T1当前入口按上面的新目录生成全部依赖。
此验证仍限定PC静态子集，不证明RV32/板端DMA/cache或真实模型质量与性能。
