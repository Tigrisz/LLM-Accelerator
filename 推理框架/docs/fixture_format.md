# A2 测试样本规范 fixture-v1

当前工具0.6.0；单样本与集合仍分别使用version1。S1历史见phase1a_baseline.md，S5当前入口见resources.md。
冻结集合 generator 的 0.1.0 是创建来源，不因工具补丁升级改写。

本格式是阶段 1A 的基础算子样本，不是最终模型包，也不是 W4A8/GGUF/AWQ/GPTQ。
接口中可描述未来量化格式，但本版只执行 float32/int32、linear/add/relu。
严格校验的可执行定义为 inference_ref/fixtures.py。

## 目录与编码

每个样本目录只有两个必需文件：manifest.json、data.bin。
manifest 是 UTF-8 JSON（生成器使用 LF），禁止重复 key、NaN/Infinity 字面量。
data.bin 是小端连续行优先二进制，不保存 Python/NumPy 对象和机器指针。
生成器不会覆盖已存在的目录。I/O 中断可能留下不完整目录，须使用新目录重试；
不完整目录不能通过读取校验。校验工具不修改输入。

suite.json 是样本集合索引，包含 format="inference-fixture-suite"、version=1、
generator 和非空 cases。每项只有 directory、manifest_sha256。
directory 是当前集合根目录下的单层目录，不得越界或重复。
全部目录/标识匹配 [a-z0-9][a-z0-9_-]{0,63}；case_id 必须等于索引目录名。
只核验索引中的样本，不执行目录中的任何脚本。未索引文件不是已核验资料。
集合最多 1000 项，JSON 最多 1 MiB，单样本 data.bin 最多 16 MiB。

## manifest 顶层（全部必需，未知字段拒绝）

| 字段 | 类型 / 规则 |
| --- | --- |
| format | 字符串 inference-fixture |
| version | 整数 1，布尔值不合法 |
| case_id | 上述合法标识 |
| provenance | kind、source、seed |
| operation | name、inputs、output、attributes |
| comparison | mode、atol、rtol |
| payload | file、byte_length、sha256 |
| tensors | 2—4 个张量记录，包含全部输入和一个参考输出 |

provenance.kind 为 manual/synthetic/external_reference；
source 为 1—512 字符的来源描述，seed 为 null 或 uint64。
external_reference 只是来源标签，不表示已经实现真实模型加载或证明来源真实。
真实模型交接仍须记录固定 checkpoint、tokenizer、环境与文件清单。

operation.name 为 linear/add/relu，inputs 是不重复的张量名称列表，
output 固定 expected，attributes 固定空对象。输入名称与 A1 契约一致。
不允许缺失引用、多余未引用张量、错误 role 或与数学输出不匹配的 shape/dtype。

comparison：
- int32：mode=exact，atol=rtol=0。
- float32：mode=abs_plus_rel，atol/rtol 为可表示为有限浮点数的非负数，不能是 bool。
- 自带基础样本使用 atol=1e-6、rtol=1e-5；加载器允许其他明确的浮点门槛。
  报告保存实际门槛，验收方需冻结所用 manifest，不能事后放宽门槛冒充通过。

payload.file 固定 data.bin；byte_length 为实际文件长度；
sha256 为原始字节的 64 位小写十六进制 SHA-256。
哈希检测文件对应与损坏，不提供真实性认证；数学正确性由 A3 另行检查。

## 张量记录（全部必需，未知字段拒绝）

| 字段 | 类型 / 规则 |
| --- | --- |
| name | 合法且唯一的标识 |
| dtype | float32 或 int32 |
| shape | 1—4 维逻辑形状，正整数数组 |
| storage_shape | 同 rank，逐维不小于 shape |
| layout | row_major |
| role | 输入为 input，expected 为 reference |
| offset | uint64，4 字节对齐 |
| byte_length | product(storage_shape) × 4 |
| alignment | 整数 4 |
| sha256 | 本张量存储区域原始字节的 SHA-256 |

单张量最多 1,048,576 个存储元素。所有张量区域必须无重叠且连续覆盖整个 payload；
禁止超界、未覆盖间隙和尾部。logical 数据是每轴从 0 开始的前缀切片。
存储区所有值有限，logical 以外的 padding 必须为数值零。
读取结果复制为只读逻辑数组，不将 padding 当作有效乘加。

## 数值规范

float32 输入是已经舍入的实际存储值。参考计算先提升到 FP64，再将输出舍入到 FP32。
这不是 FP32 逐项累加的逐位模拟，也不是 FP64 原始模型执行。
标量路径以 math.fsum 累加，NumPy 路径以 FP64 归约，可能存在低位差异，按门槛比较。
int32 使用无限精度中间值，最终越界返回 NUMERIC_OVERFLOW，不回绕或饱和。
基础格式不编码 scale、zero point、group_size、LANES 或模型名称。
增加量化/布局/算子时必须定义新能力和测试，不能静默解释未知格式。

## 三方核验与退出码

每个样本执行：保存的 expected vs 标量计算、保存的 expected vs NumPy 计算、
标量计算 vs NumPy 计算。三项都通过才将样本标记 passed。
每条报告区分输入校验失败和数值失败，并给出首个不一致坐标。
集合某个样本失败不阻断其他样本的检查；集合索引本身无效则拒绝运行。

命令行退出码：0 全部通过/生成完成；1 有样本校验或数值失败；
2 调用错误、无效索引、输出已存在或 I/O 错误。
报告不能写入输入样本目录树，已存在的报告不能覆盖。
报告标记 source=software_reference，不标记 simulation 或 board。
