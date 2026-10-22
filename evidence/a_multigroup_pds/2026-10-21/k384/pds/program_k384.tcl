# Replay of official volatile-CRAM programming commands; K384 only.
# Download only after checking the final .sbit SHA256 and build reports.
cfg_set_tcl_break -flag true
cfg_connect -ip 127.0.0.1 -port 65420
cfg_scan_chain
cfg_read_device_property -device_index 0 -mode 0
cfg_assign_file -file D:/GPT/qiansai_FPGA/fpgatest/a_multigroup_k384/prj/generate_bitstream/a_multigroup_k384_uart_board_top.sbit -device_index 0
cfg_program -device_index 0
cfg_read_device_property -device_index 0 -mode 3
cfg_disconnect
exit
