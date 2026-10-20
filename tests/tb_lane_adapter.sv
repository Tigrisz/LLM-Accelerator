module tb_lane_adapter (
    input wire         clk,
    input wire         rst_n,
    input wire         in_valid,
    output wire        in_ready,
    input wire [127:0] in_weight_data,
    input wire [255:0] in_activation_data,
    input wire         in_group_first,
    input wire         in_group_last,
    input wire [15:0]  in_row_id,
    input wire [15:0]  in_group_id,
    output wire        out_valid,
    input wire         out_ready,
    output wire [63:0] out_weight_data,
    output wire [127:0] out_activation_data,
    output wire        out_group_first,
    output wire        out_group_last,
    output wire [15:0] out_row_id,
    output wire [15:0] out_group_id
);
    lane_adapter_32_to_16 dut (
        .clk(clk), .rst_n(rst_n),
        .in_valid(in_valid), .in_ready(in_ready),
        .in_weight_data(in_weight_data),
        .in_activation_data(in_activation_data),
        .in_group_first(in_group_first), .in_group_last(in_group_last),
        .in_row_id(in_row_id), .in_group_id(in_group_id),
        .out_valid(out_valid), .out_ready(out_ready),
        .out_weight_data(out_weight_data),
        .out_activation_data(out_activation_data),
        .out_group_first(out_group_first), .out_group_last(out_group_last),
        .out_row_id(out_row_id), .out_group_id(out_group_id)
    );
endmodule
