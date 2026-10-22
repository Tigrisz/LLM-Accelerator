// Reuse the B board path, not A's paired_lane_adapter integration fixture.
module tb_multigroup_uart_board #(
    parameter integer CASE_K = 256,
    parameter integer CAPTURE_DEPTH = 3 * ((CASE_K + 127) / 128),
    parameter integer CLKS_PER_BIT = 234,
    parameter integer PDS_TOP = 0
) (
    input wire clk,
    input wire rst_n,
    output wire led_busy,
    output wire led_done,
    output wire led_pass,
    output wire led_fail,
    output wire uart_tx
);
    localparam WEIGHTS = CASE_K == 256 ?
        "build/a_multigroup/lanes16_n3_k256/weights.mem" :
        "build/a_multigroup/lanes16_n3_k384/weights.mem";
    localparam ACTIVATION = CASE_K == 256 ?
        "build/a_multigroup/lanes16_n3_k256/activation.mem" :
        "build/a_multigroup/lanes16_n3_k384/activation.mem";
    localparam EXPECTED = CASE_K == 256 ?
        "build/a_multigroup/lanes16_n3_k256/expected.mem" :
        "build/a_multigroup/lanes16_n3_k384/expected.mem";
    generate if (PDS_TOP != 0) begin : pds_path
        if (CASE_K == 256) begin : k256
            a_multigroup_k256_uart_board_top #(
                .CAPTURE_DEPTH(CAPTURE_DEPTH), .CLKS_PER_BIT(CLKS_PER_BIT),
                .WEIGHT_MEM_FILE(WEIGHTS), .ACTIVATION_MEM_FILE(ACTIVATION),
                .EXPECTED_MEM_FILE(EXPECTED)
            ) dut (
                .clk(clk), .rst_n(rst_n), .led_busy(led_busy), .led_done(led_done),
                .led_pass(led_pass), .led_fail(led_fail), .uart_tx(uart_tx)
            );
        end else begin : k384
            a_multigroup_k384_uart_board_top #(
                .CAPTURE_DEPTH(CAPTURE_DEPTH), .CLKS_PER_BIT(CLKS_PER_BIT),
                .WEIGHT_MEM_FILE(WEIGHTS), .ACTIVATION_MEM_FILE(ACTIVATION),
                .EXPECTED_MEM_FILE(EXPECTED)
            ) dut (
                .clk(clk), .rst_n(rst_n), .led_busy(led_busy), .led_done(led_done),
                .led_pass(led_pass), .led_fail(led_fail), .uart_tx(uart_tx)
            );
        end
    end else begin : parameterized_path
    fixed_slice_qwen_uart_board_top #(
        .N(3), .K(CASE_K), .CAPTURE_DEPTH(CAPTURE_DEPTH),
        .CLKS_PER_BIT(CLKS_PER_BIT),
        .WEIGHT_MEM_FILE(WEIGHTS), .ACTIVATION_MEM_FILE(ACTIVATION),
        .EXPECTED_MEM_FILE(EXPECTED)
    ) dut (
        .clk(clk), .rst_n(rst_n), .led_busy(led_busy), .led_done(led_done),
        .led_pass(led_pass), .led_fail(led_fail), .uart_tx(uart_tx)
    );
    end endgenerate
endmodule
