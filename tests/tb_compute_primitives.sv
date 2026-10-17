module tb_compute_primitives #(
    parameter integer LANES = 32
) (
    input wire [LANES*4-1:0] packed_weights,
    output wire [LANES*8-1:0] signed_weights,
    input wire signed [3:0] weight,
    input wire signed [7:0] activation,
    output wire signed [11:0] product
);
    int4_unpack #(.LANES(LANES)) unpack_dut (
        .packed_weights(packed_weights), .signed_weights(signed_weights)
    );
    mac_lane mac_dut (.weight(weight), .activation(activation), .product(product));
endmodule
