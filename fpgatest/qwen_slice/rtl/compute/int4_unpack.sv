module int4_unpack #(
    parameter integer LANES = 32
) (
    input  wire [LANES*4-1:0] packed_weights,
    output wire [LANES*8-1:0] signed_weights
);
    genvar lane;
    generate
        for (lane = 0; lane < LANES; lane = lane + 1) begin : unpack_lane
            assign signed_weights[lane*8 +: 8] =
                {{4{packed_weights[lane*4+3]}}, packed_weights[lane*4 +: 4]};
        end
    endgenerate
endmodule
