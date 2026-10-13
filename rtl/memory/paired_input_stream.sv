// Pair independent task-B sources into the single beat handshake consumed by
// task A's gemv_core.  A beat is accepted only when both sources are valid and
// the core is ready, so the weight and activation payloads cannot desynchronize.
module paired_input_stream #(
    parameter integer WEIGHT_WIDTH = 128,
    parameter integer ACTIVATION_WIDTH = 256
) (
    input  logic                         weight_valid,
    output logic                         weight_ready,
    input  logic [WEIGHT_WIDTH-1:0]      weight_data,
    input  logic                         weight_group_first,
    input  logic                         weight_group_last,
    input  logic [15:0]                  weight_row_id,
    input  logic [15:0]                  weight_group_id,

    input  logic                         activation_valid,
    output logic                         activation_ready,
    input  logic [ACTIVATION_WIDTH-1:0]  activation_data,

    output logic                         in_valid,
    input  logic                         in_ready,
    output logic [WEIGHT_WIDTH-1:0]      in_weight_data,
    output logic [ACTIVATION_WIDTH-1:0]  in_activation_data,
    output logic                         in_group_first,
    output logic                         in_group_last,
    output logic [15:0]                  in_row_id,
    output logic [15:0]                  in_group_id
);
    // The adapter is intentionally stateless.  Upstream readers/caches hold
    // their payload while ready is low; the core sees one atomic handshake.
    assign in_valid = weight_valid && activation_valid;
    assign weight_ready = in_ready && activation_valid;
    assign activation_ready = in_ready && weight_valid;

    assign in_weight_data = weight_data;
    assign in_activation_data = activation_data;
    assign in_group_first = weight_group_first;
    assign in_group_last = weight_group_last;
    assign in_row_id = weight_row_id;
    assign in_group_id = weight_group_id;
endmodule
