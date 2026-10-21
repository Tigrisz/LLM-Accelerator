// Board-side capture RAM for {row_id, group_id, partial_sum} tuples.
// Packed record format: [63:32] signed partial_sum, [31:16] group_id,
// [15:0] row_id.  The RAM is written only when capture_valid is asserted.
module result_capture_buffer #(
    parameter integer DEPTH = 256
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        clear,
    input  wire        capture_valid,
    input  wire [15:0] capture_row_id,
    input  wire [15:0] capture_group_id,
    input  wire signed [31:0] capture_partial_sum,
    input  wire [$clog2(DEPTH < 2 ? 2 : DEPTH)-1:0] peek_index,
    output wire [63:0] peek_data,
    output wire        peek_valid,
    input  wire [$clog2(DEPTH < 2 ? 2 : DEPTH)-1:0] read_index,
    output wire [63:0] read_data,
    output wire        read_valid,
    output reg [31:0]  capture_count,
    output reg         overflow
);
    localparam integer INDEX_WIDTH = (DEPTH <= 1) ? 1 : $clog2(DEPTH);
    localparam [31:0] DEPTH_U32 = DEPTH;
    reg [63:0] result_mem [0:DEPTH-1];
    wire [INDEX_WIDTH-1:0] write_index = capture_count[INDEX_WIDTH-1:0];
    wire capture_space = (capture_count < DEPTH_U32);
    wire [31:0] peek_index_u32 = {{(32-INDEX_WIDTH){1'b0}}, peek_index};
    wire [31:0] read_index_u32 = {{(32-INDEX_WIDTH){1'b0}}, read_index};

    assign peek_data = result_mem[peek_index];
    assign peek_valid = (capture_count != 0) &&
                        (peek_index_u32 < capture_count);
    assign read_data = result_mem[read_index];
    assign read_valid = (capture_count != 0) &&
                        (read_index_u32 < capture_count);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            capture_count <= 32'd0;
            overflow <= 1'b0;
        end else if (clear) begin
            capture_count <= 32'd0;
            overflow <= 1'b0;
        end else if (capture_valid) begin
            if (capture_space) begin
                result_mem[write_index] <= {capture_partial_sum,
                                             capture_group_id,
                                             capture_row_id};
                capture_count <= capture_count + 32'd1;
            end else begin
                overflow <= 1'b1;
            end
        end
    end
endmodule
