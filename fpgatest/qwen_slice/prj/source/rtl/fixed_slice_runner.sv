// Standalone board-side runner for one real W4A8 model slice.
//
// The generated .mem files are initialized into BRAM/ROM by the FPGA build.
// No host write, CPU BFM, or abstract memory model is required at runtime.
// The runner compares one INT32 partial sum for every {row, group}.  K=128
// remains the original one-group smoke path; larger K values use the same
// row-major stream with a group counter and a larger expected image.
module fixed_slice_runner #(
    parameter integer N = 1,
    parameter integer K = 128,
    parameter WEIGHT_MEM_FILE = "weights.mem",
    parameter ACTIVATION_MEM_FILE = "activation.mem",
    parameter EXPECTED_MEM_FILE = "expected.mem"
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        start,
    output wire        busy,
    output reg         done,
    output reg         pass,
    output reg         fail,
    output reg [31:0]  result_count,
    output reg signed [31:0] last_partial_sum,
    output wire        result_valid,
    output wire [15:0] result_row_id,
    output wire [15:0] result_group_id,
    output wire signed [31:0] result_partial_sum
);
    localparam integer LANES = 32;
    localparam integer GROUP_SIZE = 128;
    localparam integer GROUP_BEATS = GROUP_SIZE / LANES;
    localparam integer GROUPS = (K + GROUP_SIZE - 1) / GROUP_SIZE;
    localparam integer PADDED_K = GROUPS * GROUP_SIZE;
    localparam integer WEIGHT_BEATS = PADDED_K / LANES;
    localparam integer ACTIVATION_BEATS = PADDED_K / LANES;
    localparam integer TOTAL_RESULTS = N * GROUPS;
    localparam integer ACTIVATION_INDEX_WIDTH =
        (ACTIVATION_BEATS <= 1) ? 1 : $clog2(ACTIVATION_BEATS);
    localparam integer WEIGHT_MEM_DEPTH = N * WEIGHT_BEATS;
    localparam integer WEIGHT_INDEX_WIDTH =
        (WEIGHT_MEM_DEPTH <= 1) ? 1 : $clog2(WEIGHT_MEM_DEPTH);
    localparam integer EXPECTED_INDEX_WIDTH =
        (TOTAL_RESULTS <= 1) ? 1 : $clog2(TOTAL_RESULTS);
    // Use standard part-selects rather than parameterized sized casts.  This
    // preserves the original widths while remaining compatible with ADS.
    localparam [15:0] N_U16 = N[15:0];
    localparam [15:0] GROUPS_U16 = GROUPS[15:0];
    localparam [15:0] GROUP_BEATS_U16 = GROUP_BEATS[15:0];
    localparam [15:0] WEIGHT_BEATS_U16 = WEIGHT_BEATS[15:0];
    localparam [31:0] TOTAL_RESULTS_U32 = TOTAL_RESULTS;

    reg [127:0] weight_mem [0:N*WEIGHT_BEATS-1];
    reg [255:0] activation_mem [0:ACTIVATION_BEATS-1];
    reg [31:0] expected_mem [0:TOTAL_RESULTS-1];
    initial begin
        $readmemh(WEIGHT_MEM_FILE, weight_mem);
        $readmemh(ACTIVATION_MEM_FILE, activation_mem);
        $readmemh(EXPECTED_MEM_FILE, expected_mem);
    end

    reg running;
    reg input_active;
    reg [15:0] input_row;
    reg [15:0] input_group;
    reg [15:0] input_beat;
    wire input_valid = running && input_active;
    // Use explicitly sized indices for unpacked memories.  The loop counters
    // are protocol fields (16 bits), while Verilator otherwise sizes the
    // arithmetic/index expression from the integer array bounds.
    wire [WEIGHT_INDEX_WIDTH-1:0] input_row_index =
        input_row[WEIGHT_INDEX_WIDTH-1:0];
    wire [WEIGHT_INDEX_WIDTH-1:0] input_group_index_weight =
        input_group[WEIGHT_INDEX_WIDTH-1:0];
    wire [WEIGHT_INDEX_WIDTH-1:0] input_group_beat_index_weight =
        input_beat[WEIGHT_INDEX_WIDTH-1:0];
    wire [ACTIVATION_INDEX_WIDTH-1:0] input_group_index_activation =
        input_group[ACTIVATION_INDEX_WIDTH-1:0];
    wire [ACTIVATION_INDEX_WIDTH-1:0] input_group_beat_index_activation =
        input_beat[ACTIVATION_INDEX_WIDTH-1:0];
    wire [WEIGHT_INDEX_WIDTH-1:0] weight_mem_index =
        input_row_index * WEIGHT_BEATS_U16[WEIGHT_INDEX_WIDTH-1:0]
        + input_group_index_weight * GROUP_BEATS_U16[WEIGHT_INDEX_WIDTH-1:0]
        + input_group_beat_index_weight;
    wire [ACTIVATION_INDEX_WIDTH-1:0] activation_beat_index =
        (input_group_index_activation * GROUP_BEATS_U16[ACTIVATION_INDEX_WIDTH-1:0])
        + input_group_beat_index_activation;
    wire [EXPECTED_INDEX_WIDTH-1:0] expected_row_index =
        core_row_id[EXPECTED_INDEX_WIDTH-1:0];
    wire [EXPECTED_INDEX_WIDTH-1:0] expected_group_index =
        core_group_id[EXPECTED_INDEX_WIDTH-1:0];
    wire [EXPECTED_INDEX_WIDTH-1:0] expected_mem_index =
        expected_row_index * GROUPS_U16[EXPECTED_INDEX_WIDTH-1:0]
        + expected_group_index;
    wire [127:0] input_weight_data = weight_mem[weight_mem_index];
    wire [255:0] input_activation_data = activation_mem[activation_beat_index];
    wire input_group_first = (input_beat == 0);
    wire input_group_last = (input_beat == GROUP_BEATS_U16 - 16'd1);
    wire adapter_in_ready;
    wire adapter_out_valid;
    wire adapter_out_ready = core_in_ready;
    wire [63:0] adapter_weight_data;
    wire [127:0] adapter_activation_data;
    wire adapter_group_first, adapter_group_last;
    wire [15:0] adapter_row_id, adapter_group_id;
    wire core_in_valid = adapter_out_valid;
    wire core_in_ready;
    wire [15:0] core_row_id, core_group_id;
    wire core_out_valid;
    wire signed [31:0] core_partial_sum;
    wire result_index_valid = (core_row_id < N_U16) &&
                              (core_group_id < GROUPS_U16);
    wire result_ok = result_index_valid &&
                     (core_partial_sum == $signed(expected_mem[expected_mem_index]));

    assign result_valid = core_out_valid;
    assign result_row_id = core_row_id;
    assign result_group_id = core_group_id;
    assign result_partial_sum = core_partial_sum;

    assign busy = running && !done;

    lane_adapter_32_to_16 adapter_inst (
        .clk(clk), .rst_n(rst_n),
        .in_valid(input_valid), .in_ready(adapter_in_ready),
        .in_weight_data(input_weight_data),
        .in_activation_data(input_activation_data),
        .in_group_first(input_group_first), .in_group_last(input_group_last),
        .in_row_id(input_row), .in_group_id(input_group),
        .out_valid(adapter_out_valid), .out_ready(adapter_out_ready),
        .out_weight_data(adapter_weight_data),
        .out_activation_data(adapter_activation_data),
        .out_group_first(adapter_group_first),
        .out_group_last(adapter_group_last),
        .out_row_id(adapter_row_id), .out_group_id(adapter_group_id)
    );

    gemv_core #(.LANES(16)) core_inst (
        .clk(clk), .rst_n(rst_n),
        .in_valid(core_in_valid), .in_ready(core_in_ready),
        .weight_data(adapter_weight_data),
        .activation_data(adapter_activation_data),
        .group_first(adapter_group_first), .group_last(adapter_group_last),
        .row_id(adapter_row_id), .group_id(adapter_group_id),
        .out_valid(core_out_valid), .out_ready(1'b1),
        .partial_sum(core_partial_sum), .out_row_id(core_row_id),
        .out_group_id(core_group_id)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            running <= 1'b0;
            input_active <= 1'b0;
            input_row <= 16'd0;
            input_group <= 16'd0;
            input_beat <= 16'd0;
            done <= 1'b0;
            pass <= 1'b0;
            fail <= 1'b0;
            result_count <= 32'd0;
            last_partial_sum <= 32'sd0;
        end else if (start && !running && !done) begin
            running <= 1'b1;
            input_active <= 1'b1;
            input_row <= 16'd0;
            input_group <= 16'd0;
            input_beat <= 16'd0;
            done <= 1'b0;
            pass <= 1'b0;
            fail <= 1'b0;
            result_count <= 32'd0;
        end else if (running) begin
            if (input_valid && adapter_in_ready) begin
                if (input_beat == GROUP_BEATS_U16 - 16'd1) begin
                    input_beat <= 16'd0;
                    if (input_group == GROUPS_U16 - 16'd1) begin
                        input_group <= 16'd0;
                        if (input_row == N_U16 - 16'd1) begin
                            input_active <= 1'b0;
                        end else begin
                            input_row <= input_row + 16'd1;
                        end
                    end else begin
                        input_group <= input_group + 16'd1;
                    end
                end else begin
                    input_beat <= input_beat + 16'd1;
                end
            end

            if (core_out_valid) begin
                result_count <= result_count + 32'd1;
                last_partial_sum <= core_partial_sum;
                if (!result_ok) fail <= 1'b1;
                if (result_count + 32'd1 >= TOTAL_RESULTS_U32) begin
                    running <= 1'b0;
                    done <= 1'b1;
                    pass <= !fail && result_ok;
                end
            end
        end
    end
endmodule
