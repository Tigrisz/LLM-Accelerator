# Qwen PDS工程入口

在PDS 2022.2-SP6.4打开`prj/prj.pds`。目标器件PG2L100H-6FBG676，
当前顶层`fixed_slice_qwen_uart_board_top`，27MHz、KEY0复位、UART TX=C24。

`prj/source/`是该工程实际引用的计算/runner源码；UART RTL通过相对路径引用
仓库根目录`rtl/debug/`与`rtl/model/`，UART约束引用根目录`constraints/`。
`prj/mem/`保留三个固化初始化文件。打开工程时不要只单独复制prj文件夹，
应保留整个仓库相对目录结构。

`rtl/`子目录是历史导入副本，当前工程不引用，暂保留以兼容旧资料；
当前改动以根目录RTL和prj.pds实际引用文件为准，勿将旧副本覆盖到工程。

`prj/generate_bitstream/`保留两个最终.sbit：

- fixed_slice_qwen_uart_board_top.sbit：当前UART实测位流。
- fixed_slice_qwen_demo_top.sbit：之前LED-only回退基线。

编译、综合、映射、布局布线等缓存停止Git跟踪，但当前电脑上保留原文件，
不影响继续查看已打开的工程。新克隆首次打开时可能需要重新执行各构建阶段，
不要把缺少已忽略缓存解释为工程源文件缺失。

重建流程见根目录`docs/uart_board_validation_2026-10-21.md`；
工具生成的历史impl.tcl不再提交，正式构建入口是`scripts/pds_uart_build.tcl`。
PDS及实板报告快照保存在根目录`evidence/`。本次整理不修改RTL功能、不重新下载位流。
