// N=16, K=2048 real-model multi-group fixed-slice test wrapper.
module tb_fixed_slice_qwen_multigroup (
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
    wire unused_result_valid;
    wire [15:0] unused_result_row_id, unused_result_group_id;
    wire signed [31:0] unused_result_partial_sum;
    fixed_slice_runner #(
        .N(16), .K(2048),
        .WEIGHT_MEM_FILE("build/fixed_slice_qwen_multigroup/weights.mem"),
        .ACTIVATION_MEM_FILE("build/fixed_slice_qwen_multigroup/activation.mem"),
        .EXPECTED_MEM_FILE("build/fixed_slice_qwen_multigroup/expected.mem")
    ) dut (
        .clk(clk), .rst_n(rst_n), .start(start), .busy(busy), .done(done),
        .pass(pass), .fail(fail), .result_count(result_count),
        .last_partial_sum(last_partial_sum),
        .result_valid(unused_result_valid), .result_row_id(unused_result_row_id),
        .result_group_id(unused_result_group_id),
        .result_partial_sum(unused_result_partial_sum)
    );
endmodule
