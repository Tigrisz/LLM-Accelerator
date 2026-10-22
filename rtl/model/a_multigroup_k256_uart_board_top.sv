// Task-A synthetic fixture only; not a Qwen model slice.
// MES2L676-100HP: reuse the validated seven-IO board wrapper and UART protocol.
module a_multigroup_k256_uart_board_top #(
    parameter integer CAPTURE_DEPTH = 6,
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
    fixed_slice_qwen_uart_board_top #(
        .N(3), .K(256), .CAPTURE_DEPTH(CAPTURE_DEPTH),
        .CLKS_PER_BIT(CLKS_PER_BIT),
        .WEIGHT_MEM_FILE(WEIGHT_MEM_FILE),
        .ACTIVATION_MEM_FILE(ACTIVATION_MEM_FILE),
        .EXPECTED_MEM_FILE(EXPECTED_MEM_FILE)
    ) board (
        .clk(clk), .rst_n(rst_n), .led_busy(led_busy), .led_done(led_done),
        .led_pass(led_pass), .led_fail(led_fail), .uart_tx(uart_tx)
    );
endmodule
