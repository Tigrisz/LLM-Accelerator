// Simulation integration fixture; host loads memory/cache directly.
// This is not the later MMIO/CPU controller.
module tb_b_integration #(
    parameter integer MEMORY_LATENCY = 2,
    parameter integer MEMORY_RANDOM_STALL = 1,
    parameter integer CACHE_MAX_K = 8192
) (
    input wire clk, rst_n, start,
    input wire [15:0] n_rows,
    input wire [31:0] k_elems,
    input wire [63:0] weight_base,
    input wire wr_valid,
    output wire wr_ready,
    input wire [63:0] wr_addr,
    input wire [127:0] wr_data,
    input wire [15:0] wr_strb,
    input wire load_start, load_valid, load_last,
    input wire [255:0] load_data,
    input wire [15:0] load_valid_elems,
    output wire load_ready, loaded,
    output wire [31:0] loaded_k,
    output wire busy, reader_done, error,
    output reg done,
    output wire out_valid,
    input wire out_ready,
    output wire signed [31:0] partial_sum,
    output wire [15:0] out_row_id, out_group_id,
    output wire dbg_in_valid, dbg_in_ready,
    output wire [127:0] dbg_weight,
    output wire [255:0] dbg_activation,
    output wire dbg_first, dbg_last,
    output wire [15:0] dbg_row, dbg_group,
    output wire dbg_req_valid, dbg_req_ready, dbg_mem_valid, dbg_mem_ready,
    output wire dbg_mem_error,
    output wire [63:0] dbg_addr,
    output wire [31:0] dbg_nbytes
);
    wire [127:0] memory_data, weight_data;
    wire memory_last, weight_valid, weight_ready, weight_first, weight_last;
    wire [15:0] weight_row, weight_group;
    wire activation_valid, activation_ready, activation_last;
    wire [255:0] activation_data;
    reg replay_pending;
    reg [15:0] replay_row;
    reg [31:0] results_seen;
    wire [31:0] total_results = {16'b0,n_rows} * ((k_elems+127)/128);

    memory_model #(.LATENCY(MEMORY_LATENCY), .RANDOM_STALL(MEMORY_RANDOM_STALL)) memory_inst (
        .clk(clk), .rst_n(rst_n), .wr_valid(wr_valid), .wr_ready(wr_ready),
        .wr_addr(wr_addr), .wr_data(wr_data), .wr_strb(wr_strb),
        .rd_req_valid(dbg_req_valid), .rd_req_ready(dbg_req_ready),
        .rd_addr(dbg_addr), .rd_nbytes(dbg_nbytes),
        .rd_data_valid(dbg_mem_valid), .rd_data_ready(dbg_mem_ready),
        .rd_data(memory_data), .rd_last(memory_last), .rd_error(dbg_mem_error)
    );
    weight_reader reader_inst (
        .clk(clk), .rst_n(rst_n), .start(start), .weight_base(weight_base),
        .n_rows(n_rows), .k_elems(k_elems), .busy(busy), .done(reader_done), .error(error),
        .rd_req_valid(dbg_req_valid), .rd_req_ready(dbg_req_ready), .rd_addr(dbg_addr),
        .rd_nbytes(dbg_nbytes), .rd_data_valid(dbg_mem_valid), .rd_data_ready(dbg_mem_ready),
        .rd_data(memory_data), .rd_last(memory_last), .rd_error(dbg_mem_error),
        .weight_valid(weight_valid), .weight_ready(weight_ready), .weight_data(weight_data),
        .group_first(weight_first), .group_last(weight_last), .row_id(weight_row), .group_id(weight_group)
    );
    activation_cache #(.MAX_K(CACHE_MAX_K)) cache_inst (
        .clk(clk), .rst_n(rst_n), .load_start(load_start), .load_valid(load_valid),
        .load_ready(load_ready), .load_data(load_data), .load_valid_elems(load_valid_elems),
        .load_last(load_last), .loaded(loaded), .loaded_k(loaded_k),
        .read_start(start || replay_pending), .read_valid(activation_valid),
        .read_ready(activation_ready), .read_data(activation_data), .read_last(activation_last)
    );
    paired_input_stream pair_inst (
        .weight_valid(weight_valid), .weight_ready(weight_ready), .weight_data(weight_data),
        .weight_group_first(weight_first), .weight_group_last(weight_last),
        .weight_row_id(weight_row), .weight_group_id(weight_group),
        .activation_valid(activation_valid), .activation_ready(activation_ready), .activation_data(activation_data),
        .in_valid(dbg_in_valid), .in_ready(dbg_in_ready), .in_weight_data(dbg_weight),
        .in_activation_data(dbg_activation), .in_group_first(dbg_first), .in_group_last(dbg_last),
        .in_row_id(dbg_row), .in_group_id(dbg_group)
    );
    gemv_core core_inst (
        .clk(clk), .rst_n(rst_n), .in_valid(dbg_in_valid), .in_ready(dbg_in_ready),
        .weight_data(dbg_weight), .activation_data(dbg_activation),
        .group_first(dbg_first), .group_last(dbg_last), .row_id(dbg_row), .group_id(dbg_group),
        .out_valid(out_valid), .out_ready(out_ready), .partial_sum(partial_sum),
        .out_row_id(out_row_id), .out_group_id(out_group_id)
    );
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            replay_pending<=0; replay_row<=0; results_seen<=0; done<=0;
        end else begin
            replay_pending<=0;
            if(start) begin replay_row<=0; results_seen<=0; done<=0; end
            else begin
                if(activation_valid && activation_ready && activation_last && replay_row+16'd1<n_rows) begin
                    replay_pending<=1;
                    replay_row<=replay_row+16'd1;
                end
                if(out_valid && out_ready) begin
                    results_seen<=results_seen+1;
                    if(results_seen+1==total_results) done<=1;
                end
            end
        end
    end
endmodule
