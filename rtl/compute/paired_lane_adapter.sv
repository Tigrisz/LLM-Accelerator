// Paired 32-element storage beat to 16/32-element compute stream.
// For 16 lanes, retain the upstream beat until BOTH halves are consumed.
// Upstream must obey ready/valid stability. No storage format changes.
module paired_lane_adapter #(
    parameter integer LANES = 32
) (
    input wire clk, rst_n,
    input wire s_valid,
    output wire s_ready,
    input wire [127:0] s_weight,
    input wire [255:0] s_activation,
    input wire s_first, s_last,
    input wire [15:0] s_row, s_group,
    output wire m_valid,
    input wire m_ready,
    output wire [LANES*4-1:0] m_weight,
    output wire [LANES*8-1:0] m_activation,
    output wire m_first, m_last,
    output wire [15:0] m_row, m_group
);
    assign m_row = s_row;
    assign m_group = s_group;
    assign m_valid = rst_n && s_valid;
    generate
        if (LANES == 16) begin : split
            reg high_half;
            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) high_half <= 1'b0;
                else if (m_valid && m_ready) high_half <= !high_half;
            end
            assign s_ready = rst_n && high_half && m_ready;
            assign m_weight = high_half ? s_weight[127:64] : s_weight[63:0];
            assign m_activation = high_half ? s_activation[255:128] : s_activation[127:0];
            assign m_first = s_first && !high_half;
            assign m_last = s_last && high_half;
        end else begin : direct_path
            // clk participates in the interface for the split configuration.
            wire unused_clk = clk;
            assign s_ready = rst_n && m_ready;
            assign m_weight = s_weight;
            assign m_activation = s_activation;
            assign m_first = s_first;
            assign m_last = s_last;
            initial begin
                if (LANES != 32) $fatal(1, "LANES must be 16 or 32");
            end
        end
    endgenerate
endmodule
