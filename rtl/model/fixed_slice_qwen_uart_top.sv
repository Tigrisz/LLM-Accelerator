// Optional board wrapper for Qwen N=16, K=2048 result readback.
// The existing four-LED demo top remains unchanged.  This wrapper adds a
// dedicated UART TX output once the board pin and baud-clock constraints are
// assigned in the PDS project.
module fixed_slice_qwen_uart_top #(
    parameter integer N = 16,
    parameter integer K = 2048,
    parameter integer CAPTURE_DEPTH = 256,
    parameter integer CLKS_PER_BIT = 234,
    parameter WEIGHT_MEM_FILE = "build/fixed_slice_qwen_multigroup/weights.mem",
    parameter ACTIVATION_MEM_FILE = "build/fixed_slice_qwen_multigroup/activation.mem",
    parameter EXPECTED_MEM_FILE = "build/fixed_slice_qwen_multigroup/expected.mem"
) (
    input wire clk,
    input wire rst_n,
    output wire led_busy,
    output wire led_done,
    output wire led_pass,
    output wire led_fail,
    output wire uart_tx,
    output wire [31:0] result_count,
    output wire signed [31:0] last_partial_sum,
    output wire [31:0] capture_count,
    output wire capture_overflow,
    output wire uart_busy,
    output wire uart_done
);
    wire result_valid;
    wire [15:0] result_row_id;
    wire [15:0] result_group_id;
    wire signed [31:0] result_partial_sum;
    reg uart_started;
    wire capture_clear = !rst_n;
    wire uart_start = led_done && !uart_started;

    wire [$clog2(CAPTURE_DEPTH < 2 ? 2 : CAPTURE_DEPTH)-1:0] peek_index =
        {$clog2(CAPTURE_DEPTH < 2 ? 2 : CAPTURE_DEPTH){1'b0}};
    wire [63:0] unused_peek_data;
    wire unused_peek_valid;


    fixed_slice_runner #(
        .N(N), .K(K),
        .WEIGHT_MEM_FILE(WEIGHT_MEM_FILE),
        .ACTIVATION_MEM_FILE(ACTIVATION_MEM_FILE),
        .EXPECTED_MEM_FILE(EXPECTED_MEM_FILE)
    ) runner (
        .clk(clk), .rst_n(rst_n), .start(rst_n),
        .busy(led_busy), .done(led_done), .pass(led_pass), .fail(led_fail),
        .result_count(result_count), .last_partial_sum(last_partial_sum),
        .result_valid(result_valid), .result_row_id(result_row_id),
        .result_group_id(result_group_id),
        .result_partial_sum(result_partial_sum)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            uart_started <= 1'b0;
        end else if (led_done) begin
            uart_started <= 1'b1;
        end
    end

    result_capture_uart #(
        .DEPTH(CAPTURE_DEPTH),
        .CLKS_PER_BIT(CLKS_PER_BIT)
    ) result_readback (
        .clk(clk), .rst_n(rst_n), .capture_clear(capture_clear),
        .capture_valid(result_valid),
        .capture_row_id(result_row_id),
        .capture_group_id(result_group_id),
        .capture_partial_sum(result_partial_sum),
        .tx_start(uart_start),
        .peek_index(peek_index),
        .peek_data(unused_peek_data), .peek_valid(unused_peek_valid),
        .capture_count(capture_count), .overflow(capture_overflow),
        .uart_tx(uart_tx), .uart_busy(uart_busy), .uart_done(uart_done)
    );
endmodule
