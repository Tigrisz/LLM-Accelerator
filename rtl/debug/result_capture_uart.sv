// Combines the result capture RAM and UART serializer.
module result_capture_uart #(
    parameter integer DEPTH = 256,
    parameter integer CLKS_PER_BIT = 234
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
    localparam integer INDEX_WIDTH = (DEPTH <= 1) ? 1 : $clog2(DEPTH);
    wire [INDEX_WIDTH-1:0] uart_read_index;
    wire [63:0] uart_read_data;
    wire uart_read_valid;

    result_capture_buffer #(.DEPTH(DEPTH)) capture_mem (
        .clk(clk), .rst_n(rst_n), .clear(capture_clear),
        .capture_valid(capture_valid),
        .capture_row_id(capture_row_id),
        .capture_group_id(capture_group_id),
        .capture_partial_sum(capture_partial_sum),
        .peek_index(peek_index), .peek_data(peek_data),
        .peek_valid(peek_valid), .capture_count(capture_count),
        .overflow(overflow),
        .read_index(uart_read_index), .read_data(uart_read_data),
        .read_valid(uart_read_valid)
    );

    result_uart_tx #(
        .CLKS_PER_BIT(CLKS_PER_BIT),
        .INDEX_WIDTH(INDEX_WIDTH)
    ) uart_tx_inst (
        .clk(clk), .rst_n(rst_n), .start(tx_start),
        .record_count(capture_count),
        .read_index(uart_read_index),
        .read_data(uart_read_data), .read_valid(uart_read_valid),
        .tx(uart_tx), .busy(uart_busy), .done(uart_done)
    );
endmodule
