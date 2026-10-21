module tb_fixed_slice_uart_board #(
    parameter integer CAPTURE_DEPTH = 256,
    parameter integer CLKS_PER_BIT = 234
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
        .CAPTURE_DEPTH(CAPTURE_DEPTH), .CLKS_PER_BIT(CLKS_PER_BIT),
        .WEIGHT_MEM_FILE("fpgatest/qwen_slice/prj/mem/weights.mem"),
        .ACTIVATION_MEM_FILE("fpgatest/qwen_slice/prj/mem/activation.mem"),
        .EXPECTED_MEM_FILE("fpgatest/qwen_slice/prj/mem/expected.mem")
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .led_busy(led_busy), .led_done(led_done),
        .led_pass(led_pass), .led_fail(led_fail), .uart_tx(uart_tx)
    );
endmodule
