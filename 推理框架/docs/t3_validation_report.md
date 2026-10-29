# T3 PC验证记录

运行时0.6.0，纯C native ABI2；无模型/量化绑定，目标工具链/布局/栈峰值未知。

- 初始3专项因缺新类型/入口/ABI检查RED，实现后普通/sanitizer和旧ABI拒绝GREEN。
- 原174项实际运行174/174无跳过，build/t3_framework_pre_review/result.json；原Python测试源和C数值核心未改。
- 工具26/26无跳过（原20+T3新增6），build/t3_tools_pre_review/result.json；最大4096张量/1024节点真实C链、free检查区后run、预算拒绝恢复、无分配器/旧入口符号均通过。
- 第一轮新副本原174/工具26/54样本/双链/24项200轮压力通过，但S6公式漏计T字节state，整体失败；证据build/t3_pre_review。补齐公式后当前源+匹配新库的S6重验通过：54样本、324比较、28查询负控、8其他负控、4模板、资源归零，build/t3_intake_recheck。
- 同GCC15.2.0参数PC实测：context sizeof 20672→200字节；inspect单函数编译frame 32928→192字节；bind frame 448→480，新增read_info frame80。报告build/t3_metadata_pre_review/report.json，未把frame当调用链/运行峰值。
- T2历史来源审计通过（54/43/13未知/6预算null），build/t3_target_pre_review.json。准备一次独立只读审查，之后最终新副本验收。

上述为预审过程；审查与最终正式结论如下。

## 审查修复（2026-10-26）

一次只读独立审查0 Critical/1 Important/1 Minor：host可选profile分配失败错误中止，以及“必需前缀”描述未限定元数据。用户明确授权同时处理。
仅profile的预算拒绝/注入分配失败，在普通和ASan/UBSan的四组合中实际复现status4失败；修复后执行成功、输出[20,-25]、completed=4、profile_status=4/profile_available=false/complete=false，全部资源归零。
容量契约明确元数据前缀与arena整段互斥；原生用例确认仅未使用arena尾部重叠也拒绝，未降低检查。
全部工具27/27无跳过，build/t3_tools_review_fix/result.json；未二次独立复审，待最终新干净副本与收据。

## 最终验收（2026-10-26）

命令：`python3 -B tools/reproduce.py --output build/t3_final --iterations 200`，WSL/Linux。
顶层build/t3_final/report.json：passed=true、child_exit_code=0；初始无build/.git，未复制历史构建。
当前源与新副本274输入在运行完成时集合/指纹一致；1116产物SHA256被收录。完成后仅本plan/report/progress收尾，代码/输入/资料与受测副本不变，差异列入T3收据。

- 原固定174/174、工具27/27均通过，无跳过/失败/错误；新增T3工具7项，包含普通/ASan/UBSan最大4096张量/1024节点整链及profile四故障组合。
- 54/54样本，C独立/适配结果与参考对齐；双类型四节点链各正常/零输入共4条记录，普通与sanitizer均通过。
- 24/24压力探针各200轮，2400个重复成功任务、40个分配故障位置；两后端各50次恢复拒绝、2次close尝试，确认释放后资源归零。
- 原生3测试×普通/sanitizer共6运行通过；C资源程序两种构建各1000轮及6故障点；没有sanitizer诊断。新增T3专项另计，不混为上述6次。
- S6：54样本/324参考比较、28查询负控类、8其他负控、4模板pending，资源归零。T2：43来源/27 blob/54约束/13未知通过，6类目标预算仍null。

环境为WSL Ubuntu x86_64、Python3.14.4、NumPy2.3.5、GCC15.2.0；PC测量见同副本build/acceptance/static_metadata/report.json：

| 项目 | T2 | T3 | 口径 |
| --- | ---: | ---: | --- |
| sizeof(irs_context) | 20672 | 200 | 本机编译布局，字节 |
| inspect函数frame | 32928 | 192 | GCC .su，O2/fno-inline/fno-omit-frame-pointer等同参数 |
| bind函数frame | 448 | 480 | 同上，显式记录此项增加 |

检查区4T字节为调用方临时内存，状态T字节常驻；不等于总内存只剩200字节。完整调用链/ISR/线程运行峰值没有测，PC运行峰值及目标工具链/布局/栈峰值均留null。

完整性检查保护原Python测试源、109冻结输入、ir_core头/源/测试、T2九份旧源；核对S1—S6/T1/T2原收据与证据SHA。本轮汇总build/t3_validation_final/report.json，完整性build/t3_final_integrity.json，基线build/t3_baseline.json和.sha256。
T3已完成PC范围，无延期审查项；ABI2调用方需要迁移重编译。没有目标/RV32/实板/真实模型就绪结论，未提交/推送。

目标工具/ELF、布局、运行栈高水位、DDR/cache/DMA/实板/模型推理未验证；PC .su各函数frame不当作峰值。T2历史资料已固定旧源码，不覆盖历史build证据。
