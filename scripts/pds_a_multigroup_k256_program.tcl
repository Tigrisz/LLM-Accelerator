# Only the audited K256 SRAM/CRAM bitstream. No Flash/eFuse operations.
cfg_set_tcl_break -flag true
if {![info exists env(PDS_A_K256_BITSTREAM)]} {
    error {Set PDS_A_K256_BITSTREAM to the validated K256 .sbit file}
}
set a_sbit [file normalize $env(PDS_A_K256_BITSTREAM)]
if {[file tail $a_sbit] ne "a_multigroup_k256_uart_board_top.sbit" || ![file readable $a_sbit]} {
    error {Expected the validated a_multigroup_k256_uart_board_top.sbit}
}
cfg_connect -ip 127.0.0.1 -port 65420
cfg_scan_chain
cfg_read_device_property -device_index 0 -mode 0
cfg_assign_file -file $a_sbit -device_index 0
cfg_program -device_index 0
cfg_read_device_property -device_index 0 -mode 3
cfg_disconnect
exit
