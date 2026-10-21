# Run after pds_uart_setup.tcl in the current PDS project.
compile -force_to_run
synthesize -ads -selected_syn_tool_opt 2
dev_map
pnr
report_timing
gen_bit_stream -scbv {High Voltage}
save_project
