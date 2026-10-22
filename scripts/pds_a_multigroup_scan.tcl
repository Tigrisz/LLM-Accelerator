# Read-only JTAG scan. No cfg_program, Flash or eFuse operations.
cfg_set_tcl_break -flag true
cfg_connect -ip 127.0.0.1 -port 65420
cfg_scan_chain
cfg_read_device_property -device_index 0 -mode 0
cfg_disconnect
exit
