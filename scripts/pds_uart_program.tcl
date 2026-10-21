# Volatile FPGA CRAM programming only. No Flash or eFuse operations.
# Execute from repository root using the PDS cdt_cfg_shell.exe tool.
cfg_set_tcl_break -flag true
cfg_connect -ip 127.0.0.1 -port 65420
cfg_scan_chain
cfg_read_device_property -device_index 0 -mode 0
cfg_assign_file -file D:/GPT/qiansai_FPGA/fpgatest/qwen_slice/prj/generate_bitstream/fixed_slice_qwen_uart_board_top.sbit -device_index 0
cfg_program -device_index 0
cfg_read_device_property -device_index 0 -mode 3
cfg_disconnect
exit
