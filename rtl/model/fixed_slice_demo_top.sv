// Generic board-facing wrapper for a generated fixed model slice.
// Tie the clock/reset to the board and route the four status outputs to LEDs,
// a UART status block, or a board-specific debug register.
module fixed_slice_demo_top #(
    parameter integer N = 1,
    parameter integer K = 128,
    parameter WEIGHT_MEM_FILE = "weights.mem",
    parameter ACTIVATION_MEM_FILE = "activation.mem",
    parameter EXPECTED_MEM_FILE = "expected.mem"
) (
    input wire clk,
    input wire rst_n,
    output wire led_busy,
    output wire led_done,
    output wire led_pass,
    output wire led_fail,
    output wire [31:0] result_count,
    output wire signed [31:0] last_partial_sum
);
    wire unused_result_valid;
    wire [15:0] unused_result_row_id, unused_result_group_id;
    wire signed [31:0] unused_result_partial_sum;
    fixed_slice_runner #(
        .N(N), .K(K),
        .WEIGHT_MEM_FILE(WEIGHT_MEM_FILE),
        .ACTIVATION_MEM_FILE(ACTIVATION_MEM_FILE),
        .EXPECTED_MEM_FILE(EXPECTED_MEM_FILE)
    ) runner (
        .clk(clk), .rst_n(rst_n), .start(rst_n), .busy(led_busy),
        .done(led_done), .pass(led_pass), .fail(led_fail),
        .result_count(result_count), .last_partial_sum(last_partial_sum),
        .result_valid(unused_result_valid), .result_row_id(unused_result_row_id),
        .result_group_id(unused_result_group_id),
        .result_partial_sum(unused_result_partial_sum)
    );
endmodule
