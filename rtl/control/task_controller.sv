// Task-level controller for one preloaded activation-cache execution.
// A reader completion is not a task completion: DONE is asserted only after
// the final result has been accepted by the downstream result interface.
module task_controller #(
    parameter integer CACHE_MAX_K = 8192,
    parameter integer GROUP_SIZE = 128
) (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         start_request,
    input  wire         clear_status,
    input  wire [15:0]  n_rows,
    input  wire [31:0]  k_elems,
    input  wire         cache_loaded,
    input  wire [31:0]  cache_loaded_k,
    input  wire         reader_error,
    input  wire         activation_valid,
    input  wire         activation_ready,
    input  wire         activation_last,
    input  wire         result_valid,
    input  wire         result_ready,
    output reg          reader_start,
    output reg          cache_read_start,
    output wire         busy,
    output reg          done,
    output reg          error,
    output reg  [7:0]   error_code,
    output reg  [31:0]  cycle_count,
    output reg  [31:0]  result_count,
    output wire         result_pending
);
    localparam [7:0] ERR_NONE            = 8'd0;
    localparam [7:0] ERR_N_ZERO          = 8'd1;
    localparam [7:0] ERR_K_ZERO          = 8'd2;
    localparam [7:0] ERR_CACHE_CAPACITY  = 8'd3;
    localparam [7:0] ERR_ACT_NOT_LOADED  = 8'd4;
    localparam [7:0] ERR_BUSY_START     = 8'd5;
    localparam [7:0] ERR_READER         = 8'd6;
    localparam [7:0] ERR_ACT_LENGTH     = 8'd7;

    localparam [2:0] ST_IDLE  = 3'd0;
    localparam [2:0] ST_RUN   = 3'd1;
    localparam [2:0] ST_DONE  = 3'd2;
    localparam [2:0] ST_ERROR = 3'd3;

    reg [2:0] state;
    reg [15:0] replay_row;
    localparam [63:0] GROUP_SIZE_U64 = 64'(GROUP_SIZE);
    localparam [63:0] CACHE_MAX_K_U64 = 64'(CACHE_MAX_K);
    wire [63:0] k_elems_u64 = {32'd0, k_elems};
    wire [63:0] groups_per_row = (k_elems_u64 + 64'd127) / GROUP_SIZE_U64;
    wire [63:0] padded_k = groups_per_row * GROUP_SIZE_U64;
    wire [31:0] expected_results = groups_per_row[31:0] * {16'd0, n_rows};

    assign busy = (state == ST_RUN);
    assign result_pending = result_valid;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state           <= ST_IDLE;
            replay_row      <= 16'd0;
            reader_start    <= 1'b0;
            cache_read_start <= 1'b0;
            done            <= 1'b0;
            error           <= 1'b0;
            error_code      <= ERR_NONE;
            cycle_count     <= 32'd0;
            result_count    <= 32'd0;
        end else begin
            reader_start     <= 1'b0;
            cache_read_start <= 1'b0;

            if (clear_status && state != ST_RUN) begin
                state      <= ST_IDLE;
                done       <= 1'b0;
                error      <= 1'b0;
                error_code <= ERR_NONE;
                cycle_count <= 32'd0;
                result_count <= 32'd0;
            end else begin
            // Status clear has priority over the old state value. The case
            // below must not re-apply ST_ERROR/ST_DONE on this same edge.
            case (state)
                ST_IDLE, ST_DONE: begin
                    if (start_request) begin
                        if (n_rows == 16'd0) begin
                            state <= ST_ERROR; error <= 1'b1; error_code <= ERR_N_ZERO;
                        end else if (k_elems == 32'd0) begin
                            state <= ST_ERROR; error <= 1'b1; error_code <= ERR_K_ZERO;
                        end else if (padded_k > CACHE_MAX_K_U64) begin
                            state <= ST_ERROR; error <= 1'b1; error_code <= ERR_CACHE_CAPACITY;
                        end else if (!cache_loaded) begin
                            state <= ST_ERROR; error <= 1'b1; error_code <= ERR_ACT_NOT_LOADED;
                        end else if (cache_loaded_k != k_elems) begin
                            state <= ST_ERROR; error <= 1'b1; error_code <= ERR_ACT_LENGTH;
                        end else begin
                            state        <= ST_RUN;
                            done         <= 1'b0;
                            error        <= 1'b0;
                            error_code   <= ERR_NONE;
                            cycle_count  <= 32'd0;
                            result_count <= 32'd0;
                            replay_row   <= 16'd0;
                            reader_start <= 1'b1;
                            cache_read_start <= 1'b1;
                        end
                    end
                end
                ST_RUN: begin
                    cycle_count <= cycle_count + 32'd1;
                    if (start_request && !error) begin
                        // A second start never silently restarts a live task.
                        error      <= 1'b1;
                        error_code <= ERR_BUSY_START;
                    end
                    if (reader_error) begin
                        state      <= ST_ERROR;
                        error      <= 1'b1;
                        error_code <= ERR_READER;
                    end else begin
                        if (activation_valid && activation_ready && activation_last &&
                            (replay_row + 16'd1 < n_rows)) begin
                            replay_row       <= replay_row + 16'd1;
                            cache_read_start <= 1'b1;
                        end
                        if (result_valid && result_ready) begin
                            result_count <= result_count + 32'd1;
                            if ((result_count + 32'd1) >= expected_results) begin
                                state <= ST_DONE;
                                done  <= 1'b1;
                            end
                        end
                    end
                end
                ST_ERROR: begin
                    // Error is sticky until software writes CTRL.CLEAR_STATUS.
                    state <= ST_ERROR;
                end
                default: state <= ST_IDLE;
            endcase
            end
        end
    end
endmodule
