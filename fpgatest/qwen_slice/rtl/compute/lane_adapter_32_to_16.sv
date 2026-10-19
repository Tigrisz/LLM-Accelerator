// Split one atomic 32-lane W4A8 beat into two 16-lane beats.
//
// The upstream protocol is intentionally held as one pair: a new input is
// accepted only when both halves of the previous pair have been consumed.
// This preserves the paired weight/activation handshake and keeps every
// output field stable while out_ready is low.
module lane_adapter_32_to_16 (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         in_valid,
    output wire         in_ready,
    input  wire [127:0] in_weight_data,
    input  wire [255:0] in_activation_data,
    input  wire         in_group_first,
    input  wire         in_group_last,
    input  wire [15:0]  in_row_id,
    input  wire [15:0]  in_group_id,
    output wire         out_valid,
    input  wire         out_ready,
    output wire [63:0]  out_weight_data,
    output wire [127:0] out_activation_data,
    output wire         out_group_first,
    output wire         out_group_last,
    output wire [15:0]  out_row_id,
    output wire [15:0]  out_group_id
);
    reg         pending;
    reg         half_select;
    reg [127:0] weight_hold;
    reg [255:0] activation_hold;
    reg         group_first_hold;
    reg         group_last_hold;
    reg [15:0]  row_hold;
    reg [15:0]  group_hold;

    assign in_ready = rst_n && !pending;
    assign out_valid = pending;
    assign out_weight_data = half_select ? weight_hold[127:64] : weight_hold[63:0];
    assign out_activation_data = half_select ? activation_hold[255:128] : activation_hold[127:0];
    assign out_group_first = pending && !half_select && group_first_hold;
    assign out_group_last = pending && half_select && group_last_hold;
    assign out_row_id = row_hold;
    assign out_group_id = group_hold;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pending          <= 1'b0;
            half_select      <= 1'b0;
            weight_hold      <= 128'b0;
            activation_hold  <= 256'b0;
            group_first_hold <= 1'b0;
            group_last_hold  <= 1'b0;
            row_hold         <= 16'b0;
            group_hold       <= 16'b0;
        end else if (!pending) begin
            if (in_valid && in_ready) begin
                pending          <= 1'b1;
                half_select      <= 1'b0;
                weight_hold      <= in_weight_data;
                activation_hold  <= in_activation_data;
                group_first_hold <= in_group_first;
                group_last_hold  <= in_group_last;
                row_hold         <= in_row_id;
                group_hold       <= in_group_id;
            end
        end else if (out_valid && out_ready) begin
            if (!half_select) begin
                half_select <= 1'b1;
            end else begin
                pending     <= 1'b0;
                half_select <= 1'b0;
            end
        end
    end
endmodule
