// UART serializer for a captured result frame.
// Frame bytes, all multi-byte fields little endian:
//   A5 5A 01 count[31:0] records[8*count] 5A A5
// Each record is row_id[15:0], group_id[15:0], partial_sum[31:0].
module result_uart_tx #(
    parameter integer CLKS_PER_BIT = 234,
    parameter integer INDEX_WIDTH = 8
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,
    input  wire [31:0] record_count,
    output reg [INDEX_WIDTH-1:0] read_index,
    input  wire [63:0] read_data,
    input  wire        read_valid,
    output reg         tx,
    output reg         busy,
    output reg         done
);
    localparam integer COUNT_BYTES = 7;
    reg [31:0] frame_pos;
    reg [31:0] latched_count;
    reg [7:0] current_byte;
    // bit_pos is 0..9 (start, eight data bits, stop), so five bits are
    // required before it is used as a variable index into current_byte.
    reg [4:0] bit_pos;
    reg [31:0] baud_count;
    reg byte_active;
    reg [7:0] frame_byte;
    reg [31:0] frame_record_end;

    always @* begin
        frame_record_end = COUNT_BYTES + (latched_count * 32'd8);
        frame_byte = 8'h00;
        if (frame_pos == 32'd0) begin
            frame_byte = 8'ha5;
        end else if (frame_pos == 32'd1) begin
            frame_byte = 8'h5a;
        end else if (frame_pos == 32'd2) begin
            frame_byte = 8'h01;
        end else if (frame_pos == 32'd3) begin
            frame_byte = latched_count[7:0];
        end else if (frame_pos == 32'd4) begin
            frame_byte = latched_count[15:8];
        end else if (frame_pos == 32'd5) begin
            frame_byte = latched_count[23:16];
        end else if (frame_pos == 32'd6) begin
            frame_byte = latched_count[31:24];
        end else if (frame_pos < frame_record_end) begin
            case ((frame_pos - COUNT_BYTES) & 32'd7)
                0: frame_byte = read_valid ? read_data[7:0] : 8'd0;
                1: frame_byte = read_valid ? read_data[15:8] : 8'd0;
                2: frame_byte = read_valid ? read_data[23:16] : 8'd0;
                3: frame_byte = read_valid ? read_data[31:24] : 8'd0;
                4: frame_byte = read_valid ? read_data[39:32] : 8'd0;
                5: frame_byte = read_valid ? read_data[47:40] : 8'd0;
                6: frame_byte = read_valid ? read_data[55:48] : 8'd0;
                default: frame_byte = read_valid ? read_data[63:56] : 8'd0;
            endcase
        end else if (frame_pos == frame_record_end) begin
            frame_byte = 8'h5a;
        end else begin
            frame_byte = 8'ha5;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            read_index <= {INDEX_WIDTH{1'b0}};
            tx <= 1'b1;
            busy <= 1'b0;
            done <= 1'b0;
            frame_pos <= 32'd0;
            latched_count <= 32'd0;
            current_byte <= 8'd0;
            bit_pos <= 5'd0;
            baud_count <= 32'd0;
            byte_active <= 1'b0;
        end else begin
            done <= 1'b0;
            if (!busy) begin
                tx <= 1'b1;
                byte_active <= 1'b0;
                if (start) begin
                    busy <= 1'b1;
                    frame_pos <= 32'd0;
                    latched_count <= record_count;
                    read_index <= {INDEX_WIDTH{1'b0}};
                    baud_count <= 32'd0;
                end
            end else if (!byte_active) begin
                current_byte <= frame_byte;
                byte_active <= 1'b1;
                bit_pos <= 5'd0;
                baud_count <= 32'd0;
                tx <= 1'b0;
            end else if (baud_count == CLKS_PER_BIT - 1) begin
                baud_count <= 32'd0;
                if (bit_pos == 5'd0) begin
                    tx <= current_byte[0];
                    bit_pos <= 5'd1;
                end else if (bit_pos < 5'd8) begin
                    // This branch is limited to bit_pos 1..7; use the
                    // exact 3-bit index width required by an 8-bit vector.
                    tx <= current_byte[bit_pos[2:0]];
                    bit_pos <= bit_pos + 5'd1;
                end else if (bit_pos == 5'd8) begin
                    tx <= 1'b1;
                    bit_pos <= 5'd9;
                end else begin
                    byte_active <= 1'b0;
                    tx <= 1'b1;
                    if (frame_pos == frame_record_end + 32'd1) begin
                        busy <= 1'b0;
                        done <= 1'b1;
                    end else begin
                        frame_pos <= frame_pos + 32'd1;
                        if ((frame_pos + 32'd1) == COUNT_BYTES) begin
                            read_index <= {INDEX_WIDTH{1'b0}};
                        end else if ((frame_pos + 32'd1) > COUNT_BYTES &&
                                     (frame_pos + 32'd1) < frame_record_end &&
                                     ((((frame_pos + 32'd1) - COUNT_BYTES) & 32'd7) == 0)) begin
                            read_index <= read_index + {{(INDEX_WIDTH-1){1'b0}}, 1'b1};
                        end
                    end
                end
            end else begin
                baud_count <= baud_count + 32'd1;
            end
        end
    end
endmodule
