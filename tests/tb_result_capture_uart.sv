module tb_result_capture_uart #(
    parameter integer DEPTH = 6,
    parameter integer CLKS_PER_BIT = 1
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        capture_clear,
    input  wire        capture_valid,
    input  wire [15:0] capture_row_id,
    input  wire [15:0] capture_group_id,
    input  wire signed [31:0] capture_partial_sum,
    input  wire        tx_start,
    input  wire [$clog2(DEPTH < 2 ? 2 : DEPTH)-1:0] peek_index,
    output wire [63:0] peek_data,
    output wire        peek_valid,
    output wire [31:0] capture_count,
    output wire        overflow,
    output wire        uart_tx,
    output wire        uart_busy,
    output wire        uart_done
);
    result_capture_uart #(
        .DEPTH(DEPTH),
        .CLKS_PER_BIT(CLKS_PER_BIT)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .capture_clear(capture_clear),
        .capture_valid(capture_valid),
        .capture_row_id(capture_row_id),
        .capture_group_id(capture_group_id),
        .capture_partial_sum(capture_partial_sum),
        .tx_start(tx_start),
        .peek_index(peek_index),
        .peek_data(peek_data),
        .peek_valid(peek_valid),
        .capture_count(capture_count),
        .overflow(overflow),
        .uart_tx(uart_tx),
        .uart_busy(uart_busy),
        .uart_done(uart_done)
    );
endmodule
