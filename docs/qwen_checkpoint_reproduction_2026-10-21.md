# 任务A补充：独立UART分支、模型revision与提取复现

## 交付版本

- 独立分支：`codex/qwen-uart-board-handoff`。
- 分支基线及UART主体提交：`c548e80063daf21783405adf0df3d1f56a3c63ef`。
- 干净检出输入准备修复：`906e8120616aedc1b2166725980faa26d9979758`。
- 本分支补充来源、复现证据及缺失的测试输入准备，不重写main、不重复搬运相同RTL。
- 最终补充提交号以本分支`git rev-parse HEAD`及本次回复为准。
- 用户要求本次只作本地提交，新分支由用户自行推送；不把本地分支说成已发布远程。

UART RTL位于`rtl/debug/`和`rtl/model/fixed_slice_qwen_uart*.sv`；测试和约束分别在
`tests/*uart*`、`tests/test_result_capture_uart.cpp`、`constraints/`，构建目标在Makefile。
可重建PDS工程入口为`fpgatest/qwen_slice/prj/prj.pds`，包括它引用的所有源码、
约束、mem和最终.sbit；必须保留整个仓库相对目录，不能只复制prj子目录。
可重建的工具数据库、自动备份、编译缓存不属于缺失源码，仍按.gitignore保留在本机。
PDS工程及下载步骤见`fpgatest/qwen_slice/README.md`和`docs/uart_board_validation_2026-10-21.md`。

## checkpoint来源与证据边界

模型：`Qwen/Qwen2.5-1.5B-Instruct`。

**checkpoint revision：`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`。**

本次直接检查WSL本机HF缓存：refs/main指向该revision，snapshots目录只有该snapshot。
但历史K2048提取命令没有保存revision字段，不能单凭缓存指针断言原命令已固定版本。
因此本次关闭网络读取，显式以该snapshot本地路径重新提取到独立build目录，
确认权重、激活、两种量化尺度、期望部分和，以及三个PDS.mem逐字节匹配已验收资料。
这给出可重现已交付数据的固定revision，而不是用最新线上main替换历史来源。

权重文件model.safetensors的SHA256：

```text
dd924a11b4c220f385b51ffa522daea7c9f3d850e31b162bb5661df483c6d3ee
```

模型配置、tokenizer等七个输入文件哈希及重放结果见
`evidence/model_provenance/2026-10-21/provenance.json`。不向Git提交整个模型权重缓存。

## 参数与当前重放环境

- layer=0，self_attn.o_proj，rows_start=0、N=16、cols_start=0。
- 物理K=2048；原模型有效1536列，末尾512列补零；group_size=128，共256条部分和。
- prompt为`FPGA W4A8 slice validation.`，token_index=-1。
- 对称W4A8：权重按行/组scale，激活一个scalar scale；CPU执行、eval、无采样。
- 本次重放环境：WSL Linux，Python3.14.4，torch2.14.1（runtime 2.14.1+cu130）、
  transformers5.20.1、numpy2.5.4、huggingface_hub2.2.0、tokenizers0.23.3、
  safetensors0.8.0、sentencepiece0.2.2。

以上是实际观测版本，不宣称任意不同版本/设备都能逐字节一致；复现后仍须比较哈希。
torch安装包含CUDA支持，但当前脚本未将模型或输入移入GPU。
源脚本继续使用既有`torch_dtype="auto"`；没有为补充说明改变提取或RTL计算算法。

## 固定revision复现命令（WSL，在仓库根目录）

先进入安装好上述模型依赖的环境。模型已缓存时可完全离线；未缓存时，
用snapshot_download显式下载指定revision（不是可变的main）：

```bash
cd /mnt/d/GPT/qiansai_FPGA
source .venv-qwen/bin/activate

QWEN_SNAPSHOT=$(python -c "from huggingface_hub import snapshot_download; print(snapshot_download('Qwen/Qwen2.5-1.5B-Instruct', revision='989aa7980e4cf806f80c7fef2b1adb7bc71aa306'))")

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python scripts/extract_qwen_slice.py \
  --model "$QWEN_SNAPSHOT" \
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

本机实际重放时，QWEN_SNAPSHOT明确为：
`/home/jack/.cache/huggingface/hub/models--Qwen--Qwen2.5-1.5B-Instruct/snapshots/989aa7980e4cf806f80c7fef2b1adb7bc71aa306`。
本次直接使用该缓存路径，没有重新从网络下载checkpoint。

请保持上述.mem生成在WSL/Linux执行，以产生原始LF格式。Windows Python文本输出
默认可能变成CRLF：数值相同但文件SHA256不同；本次曾定位并排除此格式差异，
最终逐字节一致的.mem来自WSL生成。本分支已用.gitattributes将.mem检出固定为LF；
对旧检出文件仍应核对仓库对象/固定交付ZIP中的原始字节，勿把换行不同误报为计算不同。

因为`--model`使用固定本地snapshot，重放config.json的model字段是本地路径，
不是原交付中的模型仓库ID。这一字段差异已单独检查；除model字段外配置一致，
其余五个量化数据文件及三个.mem均逐字节一致。旧config、旧采集、旧ZIP未被改写。

## 历史参数等效命令与本次锁定命令的区别

原K2048文档中的命令为`--model Qwen/Qwen2.5-1.5B-Instruct --rows 16 --cols 2048
--allow-zero-pad-cols`，其余参数使用脚本默认值，对应上述层、起始行列、prompt及token。
它没有固定revision；shell历史只找到K128提取命令，不把重建的K2048命令称为原始终端日志。
以后应优先使用上面的固定snapshot命令，以避免模型远程main或tokenizer随时间变化。

## 验证与给A的使用顺序

本次先在原工作区重新运行17阶段完整RTL回归通过；随后无build目录的干净检出
暴露旧K128和K2048测试未自动准备被忽略的.mem输入。已把旧K128 ROM固定到
tests/fixtures/qwen_n16_k128，两个Make目标先独立验算再准备各自输入，并增加
两个从空目标目录启动的回归测试，观察到修复前失败、修复后通过。
ROM-only fixture与tests/vectors的标准.bin/.npy向量分目录，避免被错误枚举。
这只修复构建复现依赖，不改RTL、PDS输入、量化算法或已验收位流。
修复后的完整回归及干净检出验证见新归档。
UART原始三帧及对应位流与A已独立核验的交付保持相同；不重新声称采集了新板端数据。
新重放和回归记录在`evidence/model_provenance/2026-10-21/`。

用户推送本分支后，A可在干净工作区fetch并切换到该分支，核对最终提交号，再：

1. 从完整仓库打开prj/prj.pds，确认UART顶层及所有源路径存在。
2. 用本页固定revision命令重提取，按provenance.json比较数据与.mem哈希。
3. 运行`python scripts/run_regression.py`，复核RTL协议与多组结果。
4. 已有板端bin/JSON仍使用`evidence/uart_board/2026-10-21/`，
   固定位流仍为`prj/generate_bitstream/fixed_slice_qwen_uart_board_top.sbit`。

对后续lanes16_n3_k256/384，需分别配置6/9条输出并生成对应新位流，
不能把本N16/K2048基线自动视为那两个用例已实板通过。
