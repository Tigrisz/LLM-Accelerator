# Source in the already-open fpgatest/qwen_slice/prj/prj.pds Tcl console.
# Root RTL is referenced in place; do not add a second fixed_slice_runner.
# PDS evaluates source through its own command runner; info script is empty.
# The active project's working directory is fpgatest/qwen_slice/prj.
set uart_repo [file normalize [file join [pwd] .. .. ..]]
if {![file exists [file join $uart_repo rtl model fixed_slice_qwen_uart_board_top.sv]]} {
    error {Run this script from the open fpgatest/qwen_slice/prj project}
}
foreach uart_file {
    rtl/debug/result_capture_buffer.sv
    rtl/debug/result_uart_tx.sv
    rtl/debug/result_capture_uart.sv
    rtl/model/fixed_slice_qwen_uart_top.sv
    rtl/model/fixed_slice_qwen_uart_board_top.sv
} {
    add_design [file join $uart_repo $uart_file]
}
add_constraint [file join $uart_repo constraints fixed_slice_qwen_uart_io.fdc]
# In GUI, right-click fixed_slice_qwen_uart_board_top -> Set As Top Module.
# PDS requires that selection before Compile will accept the new top.
save_project
