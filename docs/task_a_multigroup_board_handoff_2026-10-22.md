# 给任务A：K256/K384三次实板UART交接说明

打包日期：2026-10-22；原始构建和实板采集日期：2026-10-21（北京时间）。
交接ZIP：`a_multigroup_board_handoff_2026-10-22.zip`，与同名`.zip.sha256`一起发送。

## 交接结论与范围

两套用例均完成PDS编译、综合、布局布线、时序检查、位流生成、CRAM下载及三次KEY0重跑。
本次打包重新核验了原始帧、JSON、冻结文件哈希及对应位流，不重新采集、不改写旧证据。

| 用例 | N | 有效/物理K | 每行组数 | 每次结果 | 每帧字节 | 重跑 |
| --- | --- | --- | --- | --- | --- | --- |
| lanes16_n3_k256 | 3 | 256/256 | 2 | 6条 | 57 | 3次 |
| lanes16_n3_k384 | 3 | 384/384 | 3 | 9条 | 81 | 3次 |

输入来自A原交接包的确定性合成整数用例（seed=K），**不是Qwen真实模型切片**。
不要与此前N16、有效1536列/物理K2048的Qwen交接结果混用。
原始逻辑lane=16；ROM按32路打包，经B现有适配器转16路计算，不改变标签/整数结果。
group_size=128；占位scale不用于本次反量化，不应将跨组整数部分和直接当成浮点结果。

## 包内结构

```text
README.md                         本说明
handoff_manifest.json             整包文件哈希、两套用例索引和来源
SHA256SUMS.txt                    包内校验清单，含handoff_manifest.json的哈希
evidence/a_multigroup_pds/2026-10-21/
  k256/                          K256原冻结证据，未改写
  k384/                          K384原冻结证据，未改写
    board/run{1,2,3}.bin          实际板端原始UART帧
    board/run{1,2,3}.json         解码JSON，source=board
    board/run{1,2,3}_a_format.json A原capture结构的板端版本
    bitstream/*.sbit             与上述采集关联的最终位流
    rom/                        三份.mem、config和转换manifest
    pds/                        资源/时序/引脚、构建、扫描、下载日志
    rtl/                        回归日志与当时的源码指纹
    verification_manifest.json  本用例的文件哈希、三次确认、位流信息
tests/fixtures/a_multigroup/      A原始打包输入、npy、stream和simulation参考
scripts/decode_result_uart.py     已有解码/逐项比较脚本，标准库即可运行
docs/*board_validation*.md        两套原验证报告
deliveries/incoming/              A原始multigroup_handoff_7fbd0b3.zip
```

这是**数据/证据交接包，不是完整可重新综合的PDS工程发布包**。
报告中的原仓库工程/源码路径用于溯源；不在包内的完整RTL和PDS工程须另从仓库获取。
保留的`rtl/environment.json`源码哈希可用于比对源码版本，不代表包内包含全部源码。
K384保护清单还记录了原Qwen/K256仓库文件哈希；未打包的原仓库文件不应被当作包内缺件。

## 一、先验证传输和文件完整性

1. 比较ZIP的SHA256与独立收到的`.zip.sha256`，再解压到一个新的空目录。
2. 进入包含本README的目录，检查`SHA256SUMS.txt`中的每一项。

Linux/WSL：

```bash
sha256sum -c a_multigroup_board_handoff_2026-10-22.zip.sha256
# 解压后，进入包内包含README.md的根目录，再执行：
sha256sum -c SHA256SUMS.txt
```

Windows PowerShell：

```powershell
Get-FileHash .\a_multigroup_board_handoff_2026-10-22.zip -Algorithm SHA256
# 先人工对照单独收到的.zip.sha256；解压后进入包含README.md的根目录：
Get-Content .\SHA256SUMS.txt | ForEach-Object {
    $auditParts = $_ -split '  ', 2
    $auditHash = (Get-FileHash -LiteralPath $auditParts[1] -Algorithm SHA256).Hash
    if ($auditHash -ne $auditParts[0]) { throw "Hash mismatch: $($auditParts[1])" }
}
'PASS package hashes'
```

完整性校验不能独自证明物理来源，也不是数字签名；来源依据见后文。

## 二、解码并逐项比较6份原始帧

无需PDS、串口、PyTorch或Transformers。使用Python 3，在包根目录运行，例如：

```bash
python3 scripts/decode_result_uart.py evidence/a_multigroup_pds/2026-10-21/k256/board/run1.bin --source board --expected evidence/a_multigroup_pds/2026-10-21/k256/rom/expected.mem --rows 3 --groups 2
python3 scripts/decode_result_uart.py evidence/a_multigroup_pds/2026-10-21/k384/board/run1.bin --source board --expected evidence/a_multigroup_pds/2026-10-21/k384/rom/expected.mem --rows 3 --groups 3
```

对run2/run3也执行相同检查，或直接使用下一节的一次性完整审计。
不指定`--output`，避免覆盖包内原JSON；另需保存审计输出时使用新路径。
逐项检查数量、row/group范围、重复/缺失、signed INT32值及row优先/group次序。

协议v1：`A5 5A 01` + uint32LE条数 + 每条`uint16LE row_id, uint16LE group_id, int32LE partial_sum`
+ `5A A5`，总长度=`9+8*条数`。

## 三、用A原始输入独立重算，避免只相信B的expected.mem

下面审计仅需要Python 3和numpy；在包根目录用Linux/WSL Bash执行。
它重新解包INT4低nibble优先、signed INT8，逐组重算；比较原npy、PDS .mem、
三次原始UART、两种JSON和A原simulation参考，并检查三帧完全相同。不会改写文件。

```bash
python3 - <<'PY'
from pathlib import Path
import hashlib, json, struct
import numpy as np

root = Path('.')
for k, groups, size in ((256, 2, 57), (384, 3, 81)):
    fixture = root / f'tests/fixtures/a_multigroup/lanes16_n3_k{k}'
    evidence = root / f'evidence/a_multigroup_pds/2026-10-21/k{k}'
    cfg = json.loads((fixture / 'config.json').read_text())
    assert (cfg['N'], cfg['K'], cfg['padded_K'], cfg['group_size'], cfg['lanes']) == (3, k, k, 128, 16)
    weights = [v - 16 if v >= 8 else v
               for b in (fixture / 'weight_packed.bin').read_bytes()
               for v in (b & 15, b >> 4)]
    activation = [v - 256 if v >= 128 else v
                  for v in (fixture / 'activation_int8.bin').read_bytes()]
    assert len(weights) == 3 * k and len(activation) == k
    sums = [[sum(weights[r*k+i] * activation[i]
                 for i in range(g*128, (g+1)*128))
             for g in range(groups)] for r in range(3)]
    golden = np.load(fixture / 'expected_partial.npy', allow_pickle=False)
    assert golden.shape == (3, groups) and golden.dtype.kind == 'i' and golden.dtype.itemsize == 4
    assert golden.tolist() == sums
    wanted = [(r, g, sums[r][g]) for r in range(3) for g in range(groups)]
    def tuples(records):
        return [(r['row_id'], r['group_id'], r['partial_sum']) for r in records]
    reference = json.loads((fixture / 'capture.json').read_text())
    assert reference['source'] == 'simulation' and tuples(reference['results']) == wanted
    mem = [int(v, 16) for v in (evidence / 'rom/expected.mem').read_text().split()]
    assert mem == [v & 0xffffffff for _, _, v in wanted]
    manifest = json.loads((evidence / 'verification_manifest.json').read_text())
    frames = []
    for n in (1, 2, 3):
        raw = (evidence / f'board/run{n}.bin').read_bytes()
        assert len(raw) == size and raw[:3] == bytes.fromhex('a55a01') and raw[-2:] == bytes.fromhex('5aa5')
        assert struct.unpack_from('<I', raw, 3)[0] == 3 * groups
        actual = [struct.unpack_from('<HHi', raw, 7 + 8*i) for i in range(3 * groups)]
        assert actual == wanted
        decoded = json.loads((evidence / f'board/run{n}.json').read_text())
        a_format = json.loads((evidence / f'board/run{n}_a_format.json').read_text())
        assert decoded['source'] == a_format['source'] == 'board'
        assert decoded['count'] == 3 * groups and decoded['verification']['passed'] is True
        assert a_format['completed'] is True
        assert tuples(decoded['records']) == tuples(a_format['results']) == wanted
        assert hashlib.sha256(raw).hexdigest() == manifest['runs'][n-1]['sha256']
        frames.append(raw)
    assert frames[0] == frames[1] == frames[2]
    print(f'PASS K={k}: 3 resets, {3*groups} tuples/frame, {size} bytes/frame; packed inputs/NPY/MEM/UART/JSON agree')
PY
```

如需接入A现有比较器，使用各`runN_a_format.json`；其结构与A原capture一致，
但`source=board`。切勿把reference中的`source=simulation`改名冒充板端采集。

## 四、核对位流与下载记录

| 用例 | 最终位流SHA256 |
| --- | --- |
| K256 | `9f52c78c1d42c598e7e442aab9d7f15da7be9efe141a3d83aac228ecc26bb160` |
| K384 | `357bd0201b621faf553c3c46b3d750c9e3bc23348252c258f6029f14fe7efb94` |

两份位流大小均为3,791,112字节。核对相应`pds/program.log`中的被分配路径、
PG2L100H/ID 0x00602899、Program成功、done=1和完整状态字。
记录中状态均为0x081ffca0，timeout/rbcrc/aut/crc/id错误位均0；不据此作温度/电气全面验收。
这两次只写易失CRAM，不写Flash/eFuse。

K384首轮曾出现SCBV未设置的critical warning，保留在`build_initial_scbv_unset.log`。
修复为同板已验收的High Voltage后重新完整构建；**只有最终build_console.log对应位流用于下载**。
不要把首轮诊断日志误认为最终构建失败，也不要忽略该修复而使用首轮位流。
K256最终构建日志名为`build_project_console.log`，K384为`build_console.log`。

## 五、建议任务A返回的核验结论

请分别记录：ZIP/包内哈希通过；三次原始UART重新解码通过；K256每次6条、K384每次9条；
全部标签/整数部分和与A输入重算和npy一致；三次重跑一致；对应位流哈希与下载记录一致。
可以据此接入A后续逐组处理链路，但不能由此宣称完整Qwen推理或反量化精度通过。

## 来源和限制

- 六份board bin确实来自此前COM10被动采集，CP2102、115200/8N1；不是本轮重新采集。
- 每轮KEY0动作、LED1/LED2亮且LED3灭由用户分别确认；UART协议不含LED或位流ID。
- 来源关联依赖实际采集会话、用户确认及下载路径/哈希；字节等同仿真不能独立证明物理来源。
- 未单独冻结每次接收命令和精确操作时间戳；不补造这些历史记录。
- 两套验证报告保留原始写作时的仓库路径/上下文；包根README和handoff_manifest是本次打包索引。
- HEAD基准为`6c880d952ef7f54d01c94448dc0e4e1612258ced`，这些文件仍在未提交工作区；
  不能声称该提交已包含本轮实现。原Qwen工程和既有位流未变，没有commit或push。
