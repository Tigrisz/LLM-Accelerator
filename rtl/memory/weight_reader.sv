// Row/group weight reader for the v1 abstract memory protocol.
// The memory image contains every row padded to a GROUP_SIZE boundary.
module weight_reader #(
    parameter integer ADDR_WIDTH = 64,
    parameter integer DATA_WIDTH = 128,
    parameter integer GROUP_SIZE = 128
) (
    input  logic                     clk,
    input  logic                     rst_n,
    input  logic                     start,
    input  logic [ADDR_WIDTH-1:0]    weight_base,
    input  logic [15:0]              n_rows,
    input  logic [31:0]              k_elems,
    output logic                     busy,
    output logic                     done,
    output logic                     error,

    output logic                     rd_req_valid,
    input  logic                     rd_req_ready,
    output logic [ADDR_WIDTH-1:0]    rd_addr,
    output logic [31:0]              rd_nbytes,
    input  logic                     rd_data_valid,
    output logic                     rd_data_ready,
    input  logic [DATA_WIDTH-1:0]    rd_data,
    input  logic                     rd_last,
    input  logic                     rd_error,

    output logic                     weight_valid,
    input  logic                     weight_ready,
    output logic [DATA_WIDTH-1:0]    weight_data,
    output logic                     group_first,
    output logic                     group_last,
    output logic [15:0]              row_id,
    output logic [15:0]              group_id
);
    localparam integer LANES = DATA_WIDTH / 4;
    localparam integer BEATS_PER_GROUP = GROUP_SIZE / LANES;
    localparam integer GROUP_BYTES = GROUP_SIZE / 2;

    typedef enum logic [2:0] {S_IDLE, S_REQ, S_DATA, S_FINISH, S_ERROR} state_t;
    state_t state;
    logic [15:0] row_reg;
    logic [15:0] group_reg;
    logic [31:0] group_count;
    logic [31:0] row_stride_bytes;
    logic [31:0] beat_index;

    assign busy = (state != S_IDLE);
    assign rd_req_valid = (state == S_REQ);
    assign rd_addr = weight_base + row_reg * row_stride_bytes + group_reg * GROUP_BYTES;
    assign rd_nbytes = GROUP_BYTES;

    assign weight_valid = (state == S_DATA) && rd_data_valid && !rd_error;
    assign weight_data = rd_data;
    assign group_first = (beat_index == 0);
    assign group_last = (beat_index == BEATS_PER_GROUP - 1);
    assign row_id = row_reg;
    assign group_id = group_reg;
    // Drain error beats even when no activation/core consumer is ready.
    assign rd_data_ready = (state == S_DATA) && (rd_error || weight_ready);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_IDLE;
            done <= 1'b0;
            error <= 1'b0;
            row_reg <= '0;
            group_reg <= '0;
            group_count <= '0;
            row_stride_bytes <= '0;
            beat_index <= '0;
        end else begin
            done <= 1'b0;
            case (state)
                S_IDLE: begin
                    if (start) begin
                        if ((n_rows == 0) || (k_elems == 0) ||
                            (GROUP_SIZE == 0) || (GROUP_SIZE % LANES != 0)) begin
                            error <= 1'b1;
                            state <= S_ERROR;
                        end else begin
                            error <= 1'b0;
                            row_reg <= 0;
                            group_reg <= 0;
                            beat_index <= 0;
                            group_count <= (k_elems + GROUP_SIZE - 1) / GROUP_SIZE;
                            row_stride_bytes <= (((k_elems + GROUP_SIZE - 1) / GROUP_SIZE) * GROUP_SIZE) / 2;
                            state <= S_REQ;
                        end
                    end
                end

                S_REQ: begin
                    if (rd_req_valid && rd_req_ready) begin
                        beat_index <= 0;
                        state <= S_DATA;
                    end
                end

                S_DATA: begin
                    if (rd_data_valid && rd_data_ready && rd_error) begin
                        error <= 1'b1;
                        state <= S_ERROR;
                    end else if (rd_data_valid && rd_data_ready) begin
                        if (rd_last != (beat_index == BEATS_PER_GROUP - 1)) begin
                            error <= 1'b1;
                            state <= S_ERROR;
                        end else if (beat_index == BEATS_PER_GROUP - 1) begin
                            state <= S_FINISH;
                        end else begin
                            beat_index <= beat_index + 1;
                        end
                    end
                end

                S_FINISH: begin
                    if (({16'b0, group_reg} + 1) >= group_count) begin
                        if ((row_reg + 1) >= n_rows) begin
                            done <= 1'b1;
                            state <= S_IDLE;
                        end else begin
                            row_reg <= row_reg + 1;
                            group_reg <= 0;
                            beat_index <= 0;
                            state <= S_REQ;
                        end
                    end else begin
                        group_reg <= group_reg + 1;
                        beat_index <= 0;
                        state <= S_REQ;
                    end
                end

                S_ERROR: begin
                    // Sticky error until a fresh reset. A new start is not
                    // accepted here, making bad configurations observable.
                    state <= S_ERROR;
                end

                default: state <= S_IDLE;
            endcase
        end
    end
endmodule

