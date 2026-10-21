# Qwen UART实板证据归档

从本机`artifacts/uart_board/2026-10-21/`逐字节复制归档，便于Git保存；
原始采集目录与交付ZIP均保留不变。本目录不包含仿真替代数据。

- run1/run2/run3.bin：COM10实际板端原始帧，每帧2057字节、256条三元组。
- 同名JSON：已逐项比较的解码结果，source=board。
- verification_manifest.json：位流/初始化文件哈希、接收时间及用户确认的三次KEY0/LED状态。
- program.log：官方JTAG配置下载日志，不把配置done等同于计算done。
- model_slice/：对应Qwen模型切片的config、原始量化权重/激活、尺度和期望部分和。

原manifest的run文件名相对于manifest目录，位流和.mem路径相对于仓库根目录；
历史报告提到的artifacts路径是原始采集位置，当前Git归档位置为本目录。
SHA256SUMS.txt覆盖本目录除清单自身之外的全部文件。从本目录运行
`sha256sum -c SHA256SUMS.txt`可核验字节完整性。

完整报告见`docs/uart_board_capture_2026-10-21.md`；给任务A使用的独立ZIP位于
`deliveries/qwen_uart_board_handoff_2026-10-21.zip`。
