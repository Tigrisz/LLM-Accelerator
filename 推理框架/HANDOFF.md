# 推理框架交接文档

日期：2026-10-29。范围：阶段1A（A1—A7）、S1—S6及T1—T8。

本次仅新增这一份Markdown交接文档，源码及必要的原有验收资料直接提交到Git新分支；不提供额外压缩包、重复证据目录或包装校验脚本。不绑定具体模型、W4A8、分组大小及硬件并行配置。

## 当前结论和版本

已形成离线检查/规划/导出 → 纯C绑定arena执行 → Python、PC C与RV32仿真对照 → 生命周期/资源/证据验收路径。目标C运行不依赖Python，离线准备和验收编排使用Python/NumPy。

运行时0.6.0、纯C native ABI2、ir_core ABI1、IRS4BIN1描述v1、平台/后端回调API1、PC services结构ABI2。旧原生调用方需要迁移并重编译。调用方提供T字节tensor_state及4T字节临时检查区，检查区在bind返回后可以释放；arena及元数据所有权以接口契约为准。

当前执行支持linear/add/relu、FP32/INT32、连续行优先及静态shape。FP32以FP64计算后舍入FP32；INT32检查结果范围。这不是量化支持、硬件FP32逐次MAC保证或真实完整模型验收。

## 已完成工作

| 阶段 | 完成内容 |
|---|---|
| A1—A3 | 接口契约、54个冻结样本及Python标量/NumPy独立参考 |
| A4 | PC最小C算子调用链及原样本对照 |
| A5 | 自有静态模型包、内存规划、arena及会话 |
| A6 | PC模拟设备、任务生命周期、隔离及恢复 |
| A7 | 模型/会话/节点/任务/平台关联追踪 |
| S1 | 零维比较坐标修复、阶段版本和基线 |
| S2 | 静态整链能力查询、后端选择和显式回退；执行失败不重跑 |
| S3 | PC读取、对齐分配、时间与同步；短读/越界/失败/32位范围检查 |
| S4 | 离线执行描述/权重导出及独立纯C静态执行 |
| S5 | arena/C元数据/profile/trace/task资源账本及压力测试 |
| S6 | 模型需求模板、能力差距和完整内存核算 |
| T1 | 不依赖历史build的PC干净副本验收入口 |
| T2 | 有来源的工具链、ABI、内存、栈及平台约束清单 |
| T3 | caller-owned元数据、native ABI2、可选profile失败降级 |
| T4 | RV32工具链/布局/栈证据，单双发射异常定位及兼容RTL、参数收口 |
| T5—T6 | 原27 INT32和27 FP32样本的RV32单/双发射迁移 |
| T7 | 原两条四节点链的原/零输入、重复及第三节点故障恢复 |
| T8 | 同一新副本统一PC、54样本、双链、异常/容量负控及实际证据重放 |

## 验证结果与边界

T8已封存结果：

- **PC**：174/174框架测试、78/78工具测试，无跳过；54样本、两类型四节点链×原/零共4记录、24资源探针各200轮、6原生验证含3 sanitizer通过。
- **RV32仿真**：56/56主项；每例同ELF单/双发射，112个正向配置、560份有效输出；4个链故障配置、8份恢复输出及额外软浮点/数值错误探针通过。
- 保留原shape/storage_shape/布局/输入/权重。主项容量阻断、失败、未知、工具错误均0；65536字节BSS容量负控正确拒绝。
- 指定xPack GCC15.2.0-1、rv32im_zicsr_zifencei/ilp32/小端/soft ABI、portable-metadata兼容RTL。主镜像最大31744字节、BSS末最大34208；主路径观测栈最大1120字节。
- **实板未验证**，board.status=unproven、passed=null、deployment_ready=false。64KiB TCM和8KiB栈是测试布局，不是OS或模型可用预算；完整最坏栈/ISR、原始RTL全量等价、综合时序、DMA/cache/DDR及真实模型质量/性能仍未知。
- 节点按成功前缀提交，不提供整图物理回滚。状态未知时禁止输出与释放，必须确认设备静止；等待超时不是停止证明。
- T8一次独立审查5项Important已修复并回归，未二次独立复审。原中断、主动停止和工具错误记录保留，不改写为通过。

2026-10-29整理交接时，另在独立源码副本重新运行了PC完整验收：174+78测试、54样本、双链、24项200轮资源压力及6原生/3 sanitizer全部通过，源码与新副本指纹一致。本次未重新执行RV32，仿真结论来自上述T8原证据。该临时副本按用户要求清理，不作为新的长期验收基线。

原T8基线SHA256：`0dacb4286b39fcb039c26a345793774dfd98f6c2e56c5567d4c0f9eb9e67e864`。其原始索引为219份源码、109份冻结输入及4081份证据；原15阶段收据/20229次历史证据哈希核验见完整性记录。

## 文件导航

| 路径（相对推理框架根目录） | 用途 |
|---|---|
| README.md | 总入口和历史阶段说明 |
| inference_ref/ | 参考、包、规划、运行时、平台/后端、追踪和资源 |
| c/include、c/src | 数值核心、静态运行时与PC服务 |
| c/rv32/ | 启动/链接、仿真驱动及样本/故障固件 |
| fixtures/synthetic-v1/ | 原54个冻结样本，共109文件，禁止改写冒充通过 |
| tests/、tools/tests/ | 原174测试及独立工具测试 |
| tools/reproduce.py | PC干净副本完整验收 |
| tools/reproduce_total.py | PC与RV32统一干净副本验收 |
| docs/、templates/ | 契约、来源、历史报告和候选需求模板 |
| build/t8_baseline.json/.sha256 | 原T8基线与指纹 |
| build/t8_validation_final/report.json | T8最终汇总 |
| build/t8_final_verified/report.json | T8统一父收据 |
| build/t8_final_verified/workspace/build/total/report.json | 56项重放矩阵及PC/仿真/实板分层 |
| build/t8_final_verified/workspace/build/rv32_total/ | 原始UART、PC输入输出/trace、ELF/map/.su及构建参数等精选证据 |

Git分支收录原328个受测源码/数据文件、此交接文档和必要的原有T8证据；不上传整个历史build、工具链安装/压缩包、Verilator生成缓存、宿主程序/库、venv、pycache或.git。Git中的部分build文件是显式选入的历史证据，不是运行依赖。

旧报告中的绝对路径及哈希保持原样。原baseline清单也包含未上传的编译缓存、旧副本和依赖，因此在新电脑上不能要求原4081产物全部存在，也不能直接运行原封存脚本冒充新验收；请从源码重新生成新收据。原完整build保留在原电脑。

## 接手与复现

为保留源码/冻结输入的原始字节，Windows克隆时关闭autocrlf，并为深层证据路径启用longpaths：

```powershell
git -c core.autocrlf=false -c core.longpaths=true clone --branch codex/inference-framework-handoff-20261029 --single-branch https://github.com/Tigrisz/LLM-Accelerator.git LLM-handoff
git -C LLM-handoff config core.autocrlf false
git -C LLM-handoff config core.longpaths true
```

在Linux/WSL进入`LLM-handoff/推理框架`后：

```sh
python3 -B tools/reproduce.py --output build/handoff_pc_new --iterations 200
```

PC需要Python+NumPy、gcc/cc/nm及C11/ASan/UBSan。已验证环境Python3.14.4、NumPy2.3.5、GCC15.2.0及WSL Ubuntu；最低版本不代表所有组合均已验证。POSIX故障注入是完整验收的一部分，不宣称Windows原生全量验收；缺工具不能作为跳过通过。

RV32另需Verilator（原证据5.032）、make/g++及固定工具链。压缩包不随仓库分发：按`tools/target_toolchain.lock.json`中的URL、长度和SHA取得原包，或从原电脑离线复制。重新执行准备脚本，不复制含旧绝对路径的receipt。

```sh
mkdir -p build
python3 -B tools/prepare_rv32_toolchain.py \
  --archive build/xpack-riscv-none-elf-gcc-15.2.0-1-linux-x64.tar.gz \
  --output build/rv32_toolchain_install
python3 -B tools/reproduce_total.py \
  --toolchain build/rv32_toolchain_install/xpack-riscv-none-elf-gcc-15.2.0-1 \
  --output build/handoff_total_new --iterations 200
```

输出路径必须不存在，重复运行换新名称。只有整体passed/exit0算通过；容量阻断、证据不足和工具错误保留独立状态。不缩形/截断，原样本与新增测试计数分开。

## 剩余任务（建议，尚未实施）

1. T9：当前约束/版本视图和资源准入；区分历史未知与T4—T8已测证据，目标OS预算未知保持null。
2. T10：固定固件的纯C通用装载及包切换；当前仍逐例生成数据头并编译，先以内存读取源验证同ELF运行不同包。
3. T11：独立扩展分支、多输入输出、共享常量、padding、多context及容量边界；原54样本不变。
4. T12：可复用目标平台、有效时间域及有界追踪；不把cycle伪作ns，不把fence当DMA/cache维护。
5. T13：真实后端契约和模拟驱动；接口未确认不虚构寄存器，局部算子支持不冒充整链支持。
6. T14：实际板卡/bitstream/装载/内存图确认后，先裸机小链、再实际OS任务环境，分别验收。

候选模型可并行采集来源、完整拓扑/算子属性、dtype/量化规则、shape/layout、golden和内存/质量门槛，不预设LLM、tokenizer、KV缓存或低位格式。当前尚无通用外部模型导入器、量化执行、动态shape/状态或自动异构切图。

## Git交接与上传

新分支为`codex/inference-framework-handoff-20261029`，基于现有本地提交增加`推理框架/`。原工作区有496项已跟踪删除记录，因此使用独立临时Git索引建立提交，不checkout、不清理或暂存这些原有改动；原加速器提交树沿用父提交。

远程目标为`https://github.com/Tigrisz/LLM-Accelerator.git`。推送该本地分支会新建远程同名分支，不修改远程main：

```powershell
Set-Location -LiteralPath 'D:\GPT\qiansai_FPGA'
git remote get-url origin
git log -1 --oneline codex/inference-framework-handoff-20261029
git push --set-upstream origin codex/inference-framework-handoff-20261029
git ls-remote --heads origin refs/heads/codex/inference-framework-handoff-20261029
```

不需要切换当前工作区分支，也不要执行`git add .`、`git commit -a`或强推。若认证失败，需要有该仓库写权限的GitHub账号；凭据不写入本文件。若远程同名分支被他人占用，先核对，不强推。提交ID、实际推送状态以本次交接完成回复及Git远程查询为准；本文件不嵌入自身commit ID以避免循环。
