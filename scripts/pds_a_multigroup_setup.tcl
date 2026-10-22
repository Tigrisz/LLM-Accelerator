# Run with official pds_shell -file ... -work_dir <repo>/fpgatest/a_multigroup_k256/prj
# or a_multigroup_k384/prj. Does not read or save the Qwen project.
if {![info exists env(PDS_A_PROJECT_DIR)]} {
    error {Set PDS_A_PROJECT_DIR to the isolated project directory before launching pds_shell}
}
set a_project_dir [file normalize $env(PDS_A_PROJECT_DIR)]
set a_case [file tail [file dirname $a_project_dir]]
if {$a_case ni {a_multigroup_k256 a_multigroup_k384} || [file tail $a_project_dir] ne "prj"} {
    error {Use an isolated fpgatest/a_multigroup_k256/prj or k384/prj working directory}
}
set a_repo [file normalize [file join $a_project_dir .. .. ..]]
set_arch -family Logos2 -device PG2L100H -package FBG676 -speedgrade -6
foreach a_file {
    rtl/compute/int4_unpack.sv
    rtl/compute/mac_lane.sv
    rtl/compute/group_acc.sv
    rtl/compute/gemv_core.sv
    rtl/compute/lane_adapter_32_to_16.sv
    rtl/model/fixed_slice_runner.sv
    rtl/debug/result_capture_buffer.sv
    rtl/debug/result_uart_tx.sv
    rtl/debug/result_capture_uart.sv
    rtl/model/fixed_slice_qwen_uart_top.sv
    rtl/model/fixed_slice_qwen_uart_board_top.sv
} {
    add_design [file join $a_repo $a_file]
}
add_design [file join $a_repo rtl model ${a_case}_uart_board_top.sv]
add_constraint [file join $a_project_dir source constraints core27m.fdc]
add_constraint [file join $a_project_dir source constraints uart_io.fdc]
foreach a_mem {weights.mem activation.mem expected.mem} {
    if {![file readable [file join $a_project_dir mem $a_mem]]} {
        error "Missing isolated ROM: $a_mem"
    }
}
# In pds_shell -file mode the resulting .pds is saved automatically.
