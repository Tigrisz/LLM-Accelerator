module tb_fixed_slice (
    input wire clk,
    input wire rst_n,
    input wire start,
    output wire busy,
    output wire done,
    output wire pass,
    output wire fail,
    output wire [31:0] result_count,
    output wire signed [31:0] last_partial_sum
);
    fixed_slice_runner #(
        .N(1), .K(128),
        .WEIGHT_MEM_FILE("build/fixed_slice/weights.mem"),
        .ACTIVATION_MEM_FILE("build/fixed_slice/activation.mem"),
        .EXPECTED_MEM_FILE("build/fixed_slice/expected.mem")
    ) dut (
        .clk(clk), .rst_n(rst_n), .start(start), .busy(busy), .done(done),
        .pass(pass), .fail(fail), .result_count(result_count),
        .last_partial_sum(last_partial_sum)
    );
endmodule
