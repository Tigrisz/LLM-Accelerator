// Board-facing wrapper for the real Qwen N=16, K=128 fixed slice.
//
// The generic fixed_slice_demo_top remains reusable for other fixtures.  This
// wrapper supplies the board acceptance configuration and can be selected as
// the PDS top-level RTL block (or instantiated below a board-specific top).
// The .mem paths are build-time ROM/BRAM initialization inputs; no host-side
// data transfer is required after configuration.
module fixed_slice_qwen_demo_top #(
    parameter WEIGHT_MEM_FILE = "mem/weights.mem",
    parameter ACTIVATION_MEM_FILE = "mem/activation.mem",
    parameter EXPECTED_MEM_FILE = "mem/expected.mem"
) (
    input wire         clk,
    input wire         rst_n,
    output wire        led_busy,
    output wire        led_done,
    output wire        led_pass,
    output wire        led_fail
);
    fixed_slice_demo_top #(
        .N(16),
        .K(128),
        .WEIGHT_MEM_FILE(WEIGHT_MEM_FILE),
        .ACTIVATION_MEM_FILE(ACTIVATION_MEM_FILE),
        .EXPECTED_MEM_FILE(EXPECTED_MEM_FILE)
    ) qwen_slice (
        .clk(clk),
        .rst_n(rst_n),
        .led_busy(led_busy),
        .led_done(led_done),
        .led_pass(led_pass),
        .led_fail(led_fail),
        // Explicit open connections keep debug counters out of the board
        // interface while documenting that they are intentionally unused.
        .result_count(),
        .last_partial_sum()
    );
endmodule
