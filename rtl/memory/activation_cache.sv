// Simple replayable activation vector cache for Day 6.
// Load one padded INT8 vector, then replay it once per output row.
module activation_cache #(
    parameter integer LANES = 32,
    parameter integer MAX_K = 4096
) (
    input  logic                    clk,
    input  logic                    rst_n,
    input  logic                    load_start,
    input  logic                    load_valid,
    output logic                    load_ready,
    input  logic [LANES*8-1:0]      load_data,
    input  logic [15:0]             load_valid_elems,
    input  logic                    load_last,
    output logic                    loaded,
    output logic [31:0]             loaded_k,

    input  logic                    read_start,
    output logic                    read_valid,
    input  logic                    read_ready,
    output logic [LANES*8-1:0]      read_data,
    output logic                    read_last
);
    localparam integer BYTE_COUNT = LANES;
    localparam integer MAX_BEATS = MAX_K / LANES;

    logic [7:0] storage [0:MAX_K-1];
    logic [31:0] load_ptr;
    logic [31:0] read_ptr;
    logic [31:0] load_beats;
    logic [31:0] read_beats;
    logic load_active;
    logic read_active;
    integer i;

    // load_ptr counts beats, whereas MAX_K counts elements.
    assign load_ready = load_active && (load_ptr < MAX_BEATS);
    assign read_valid = read_active && loaded;
    assign read_last = read_valid && (read_ptr + 1 >= read_beats);

    always_comb begin
        read_data = '0;
        for (i = 0; i < BYTE_COUNT; i = i + 1) begin
            if ((read_ptr * BYTE_COUNT + i) < MAX_K) begin
                read_data[i*8 +: 8] = storage[read_ptr * BYTE_COUNT + i];
            end
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            load_ptr <= '0;
            read_ptr <= '0;
            load_beats <= '0;
            read_beats <= '0;
            loaded_k <= '0;
            load_active <= 1'b0;
            read_active <= 1'b0;
            loaded <= 1'b0;
        end else begin
            if (load_start) begin
                load_ptr <= 0;
                load_beats <= 0;
                loaded_k <= 0;
                load_active <= 1'b1;
                read_active <= 1'b0;
                loaded <= 1'b0;
            end

            if (load_valid && load_ready) begin
                for (i = 0; i < BYTE_COUNT; i = i + 1) begin
                    if ((i < load_valid_elems) && (load_ptr * BYTE_COUNT + i < MAX_K)) begin
                        storage[load_ptr * BYTE_COUNT + i] <= load_data[i*8 +: 8];
                    end else if ((load_ptr * BYTE_COUNT + i) < MAX_K) begin
                        storage[load_ptr * BYTE_COUNT + i] <= 8'h00;
                    end
                end
                load_ptr <= load_ptr + 1;
                load_beats <= load_beats + 1;
                loaded_k <= loaded_k + {16'b0, load_valid_elems};
                if (load_last) begin
                    load_active <= 1'b0;
                    loaded <= 1'b1;
                    read_beats <= load_beats + 1;
                end
            end

            if (read_start && loaded) begin
                read_ptr <= 0;
                read_active <= 1'b1;
            end else if (read_valid && read_ready) begin
                if (read_ptr + 1 >= read_beats) begin
                    read_active <= 1'b0;
                end else begin
                    read_ptr <= read_ptr + 1;
                end
            end
        end
    end
endmodule

