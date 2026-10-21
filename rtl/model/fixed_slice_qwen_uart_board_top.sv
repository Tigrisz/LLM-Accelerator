// MES2L676-100HP: 27 MHz D18, KEY0 C22, LED0..3, UART TX C24.
// Only these seven physical IOs are exported. Debug counters stay internal.
module fixed_slice_qwen_uart_board_top #(
    parameter integer N = 16,
    parameter integer K = 2048,
    parameter integer CAPTURE_DEPTH = N * ((K + 127) / 128),
    parameter integer CLKS_PER_BIT = 234,
    parameter WEIGHT_MEM_FILE = "mem/weights.mem",
    parameter ACTIVATION_MEM_FILE = "mem/activation.mem",
    parameter EXPECTED_MEM_FILE = "mem/expected.mem"
) (
    input wire clk,
    input wire rst_n,
    output wire led_busy,
    output wire led_done,
    output wire led_pass,
    output wire led_fail,
    output wire uart_tx
);
    localparam [31:0] TOTAL_RESULTS = N * ((K + 127) / 128);
    // Asynchronous assertion and synchronous release of the pushbutton reset.
    reg [1:0] reset_sync;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) reset_sync <= 2'b00;
        else reset_sync <= {reset_sync[0], 1'b1};
    end
    wire core_rst_n = reset_sync[1];
    wire compute_pass, compute_fail;
    wire [31:0] result_count, capture_count;
    wire capture_overflow;
    wire signed [31:0] unused_last_partial_sum;
    wire unused_uart_busy, unused_uart_done;
    wire capture_ok = !capture_overflow && (capture_count == TOTAL_RESULTS) &&
                      (result_count == TOTAL_RESULTS);
    assign led_pass = led_done && compute_pass && capture_ok;
    assign led_fail = compute_fail || capture_overflow || (led_done && !capture_ok);

    fixed_slice_qwen_uart_top #(
        .N(N), .K(K), .CAPTURE_DEPTH(CAPTURE_DEPTH),
        .CLKS_PER_BIT(CLKS_PER_BIT),
        .WEIGHT_MEM_FILE(WEIGHT_MEM_FILE),
        .ACTIVATION_MEM_FILE(ACTIVATION_MEM_FILE),
        .EXPECTED_MEM_FILE(EXPECTED_MEM_FILE)
    ) qwen_uart (
        .clk(clk), .rst_n(core_rst_n),
        .led_busy(led_busy), .led_done(led_done),
        .led_pass(compute_pass), .led_fail(compute_fail), .uart_tx(uart_tx),
        .result_count(result_count), .last_partial_sum(unused_last_partial_sum),
        .capture_count(capture_count), .capture_overflow(capture_overflow),
        .uart_busy(unused_uart_busy), .uart_done(unused_uart_done)
    );
endmodule
