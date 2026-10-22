# 给任务A：UART独立分支与模型复现资料

UART RTL、测试、约束、完整可重建PDS工程及复现资料已整理到独立分支。
用户已确认该分支推送成功。

## 分支与提交

- 仓库：`Tigrisz/LLM-Accelerator`。
- 分支：`codex/qwen-uart-board-handoff`。
- 最终提交：`6c880d952ef7f54d01c94448dc0e4e1612258ced`。
- 干净检出输入准备修复提交：`906e8120616aedc1b2166725980faa26d9979758`。
- UART主体基线提交：`c548e80063daf21783405adf0df3d1f56a3c63ef`。

可在干净工作区拉取并切换：

```bash
git fetch origin
git switch --track origin/codex/qwen-uart-board-handoff
git rev-parse HEAD
```

若本地已有同名分支，使用`git switch codex/qwen-uart-board-handoff`，
再核对HEAD是否为上述最终提交，不要覆盖未提交改动。

## 模型checkpoint与切片范围

- 模型：`Qwen/Qwen2.5-1.5B-Instruct`。
- checkpoint revision：`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`。
- 层：layer 0，`self_attn.o_proj`。
- 切片：rows_start=0、N=16、cols_start=0。
- 物理K=2048，其中有效1536列、末512列补零。
- group_size=128，每行16组，共256条signed INT32部分和。
- prompt：`FPGA W4A8 slice validation.`，token_index=-1。

历史提取没有记录revision；本次通过本机HF缓存定位该snapshot，并固定版本离线
重新提取，证明它可以逐字节复现已验收数据。未把重放命令冒充历史原始终端日志，
也未改写旧采集、旧配置或旧交付ZIP。

## 固定revision提取命令

在WSL/Linux、仓库根目录及已安装模型依赖的Python环境中执行。
本机环境可先运行`source .venv-qwen/bin/activate`；其他机器使用自己的对应环境。

```bash
SNAPSHOT=$(python -c "from huggingface_hub import snapshot_download; print(snapshot_download('Qwen/Qwen2.5-1.5B-Instruct', revision='989aa7980e4cf806f80c7fef2b1adb7bc71aa306'))")

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python scripts/extract_qwen_slice.py \
  --model "$SNAPSHOT" \
  --output build/reproduction/qwen_uart_989aa798 \
  --layer 0 --rows-start 0 --rows 16 \
  --cols-start 0 --cols 2048 --allow-zero-pad-cols \
  --prompt "FPGA W4A8 slice validation." --token-index -1

python scripts/prepare_fixed_slice_mem.py \
  build/reproduction/qwen_uart_989aa798 \
  build/reproduction/qwen_uart_989aa798_mem_wsl

python scripts/verify_board_mem.py \
  --source build/reproduction/qwen_uart_989aa798_mem_wsl \
  --target build/reproduction/qwen_uart_989aa798_mem_verified
```

snapshot_download首次未命中缓存时会下载指定revision；随后提取过程使用本地snapshot，
关闭网络读取。请在WSL/Linux生成.mem以保持原始LF字节格式；Windows Python文本输出
可能产生CRLF，数值相同但SHA256不同。

由于`--model`使用本地snapshot路径，重放config.json的model字段会是本地路径；
已确认除该字段外配置一致。不要将这一来源字段差异误认为量化数据不一致。

## 验证结果

1. 固定checkpoint重提取的五个数据文件：weight_packed.bin、activation_int8.bin、
   scales.npy、activation_scale.npy、expected_partial.npy，均与已验收资料逐字节一致。
2. WSL重新生成的weights.mem、activation.mem、expected.mem，均与已验收PDS文件
   逐字节一致；256条黄金值经独立INT4×INT8整数重算一致。
3. 修复了旧K128和多组测试对未提交build目录输入的依赖，归档原有K128测试fixture，
   新增两项空目录输入准备测试，观察到修复前失败、修复后通过。
4. 修复后从已提交源码导出干净目录，不携带原build缓存，17阶段完整RTL回归全部通过。
5. UART/计算RTL、约束、PDS工程、原位流及三次实板数据未改动。本轮未重新运行PDS
   或重新采集板端数据，沿用此前已验收的硬件证据。
6. 三次实板采集仍各为2057字节、256条结果，row_id/group_id/partial_sum全部一致，
   三帧逐字节相同；用户逐次确认LED1/LED2亮、LED3灭。任务A已独立核验通过。

对应UART位流SHA256：

```text
718330d02168d8a9af8ed09f5d24bc70e69eaad67431faef7639c3c7382eef16
```

三次板端原始帧的SHA256均为：

```text
410f0086fa79888f974e245f9ac878eaad452fdd9ee3adc5eb3f62f484077cf0
```

该结论仅针对固定W4A8模型切片，不代表完整Qwen推理、DDR吞吐或token/s，
也不能代替lanes16_n3_k256/384两套用例的后续板端验证。

## 工程与证据入口

- PDS工程：`fpgatest/qwen_slice/prj/prj.pds`。
- 当前顶层：`fixed_slice_qwen_uart_board_top`。
- UART RTL：`rtl/debug/`、`rtl/model/fixed_slice_qwen_uart*.sv`。
- 板级约束：`constraints/`及PDS工程中的`source/constraints/`。
- UART位流：`fpgatest/qwen_slice/prj/generate_bitstream/fixed_slice_qwen_uart_board_top.sbit`。
- 三次板端bin/JSON：`evidence/uart_board/2026-10-21/`。
- 模型来源、重放哈希和干净回归证据：`evidence/model_provenance/2026-10-21/`。
- 完整复现说明：`docs/qwen_checkpoint_reproduction_2026-10-21.md`。
- 原固定交付包：`deliveries/qwen_uart_board_handoff_2026-10-21.zip`。

PDS工程通过相对路径引用仓库根目录UART源码与约束，请保留完整仓库结构，
不要只复制prj子目录。可重建工具数据库和自动备份未纳入Git，不属于缺失源码。

备注：本回复文件是上述分支提交完成后另行生成的说明，不包含在其既有提交号内。
