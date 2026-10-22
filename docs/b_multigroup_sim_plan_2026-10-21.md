# B：A交接小用例转换与仿真实施记录

范围：用户已批准方案的第一、二阶段，先完成两套原始小用例数据转换与仿真。
当前不修改PDS工程、约束、Qwen基线ROM/位流，不执行commit/push。
执行位置经用户选择为当前目录的新分支codex/b-multigroup-uart-cases。
给A的未提交回复文档原样保留。

## 已批准的验收约定

- 输入包multigroup_handoff_7fbd0b3.zip，SHA256：
  6b8a17b5c3d044ba2aed992885385cb6dc9d2cd229289f2640fb643bc514dbc6。
- 原始数据是A的确定性合成整数用例，seed=K，不是Qwen真实模型切片。
- lanes16_n3_k256：N3/K256、2组/行，6条结果，UART完整帧57字节。
- lanes16_n3_k384：N3/K384、3组/行，9条结果，UART完整帧81字节。
- group_size128，INT4低nibble优先、INT8按逻辑顺序，结果signed INT32。
- 原包capture.json是A的仿真输出，不是板端数据；本轮新capture也只标simulation。
- 复用B现有32路ROM到16路计算适配器，不能用A的适配器结果代替B链路仿真。

## Task 1：数据审计和转换

创建scripts/prepare_capture_case.py，接口prepare_case(source: Path, output: Path) -> dict。
读取原始config、打包输入、expected_partial.npy、stream_reference及A的capture。
验证长度/类型/shape、补零、每条原16路beat、独立整数重算、全部标签/部分和后再输出。
不修改原config中的lanes16；生成板级配置分别记录source_lanes16、compute_lanes16、
rom_pack_lanes32，产生128-bit权重字、256-bit激活字及32-bit期望字。
输出build/a_multigroup/<case>/及带输入/输出哈希和来源的manifest。
测试tests/test_capture_case.py：两个实际用例及损坏golden、stream、长度、padding、
不支持的lane配置和输出覆盖保护；先看到失败再实现。

## Task 2：真实UART波形仿真

新增tests/tb_multigroup_uart_board.sv和tests/test_multigroup_uart_board.cpp，
参数N3、K256/384、深度6/9，复用当前board top/runner/UART，不修改计算RTL。
只采样UART TX引脚解码8N1，不读取发送器内部状态或用golden生成capture。
完整波特率分频234；三次复位重跑、发送中复位恢复、数量/标签/数值/LED状态检查。
增加深度少1的负向验证，确认溢出置FAIL且不覆盖先前记录。
scripts/check_multigroup_uart.py负责运行两种配置，解码实际仿真bin并与A原始golden
及capture逐项比较，导出simulation JSON和A格式JSON；不伪称实板通过。
Makefile提供准备、lint、独立用例及总测试入口；完整回归增加本阶段。

## 共享接口与执行门槛

Task1输出.mem和manifest供Task2使用，维度和记录数必须与编译参数一致。
原始A fixture只读，放在tests/fixtures/a_multigroup，不进入自动枚举标准向量目录。
新的仿真结果放在build/reports/a_multigroup，不覆盖旧Qwen仿真/实板数据。
完成后运行完整RTL回归并进行独立代码审查；通过后才具备接入PDS的条件。
后续板端阶段需分别生成位流、三次实际KEY0采集，并由A独立核验，当前不提前宣称完成。
