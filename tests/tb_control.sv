// CPU-facing system-control fixture. The C++ test drives the internal bus
// and host preload ports as a small CPU BFM (bus functional model).
module tb_control #(
    parameter integer MEMORY_LATENCY = 2,
    parameter integer MEMORY_RANDOM_STALL = 1,
    parameter integer CACHE_MAX_K = 8192,
    parameter integer LANES = 32
) (
    input wire clk,
    input wire rst_n,
    input wire bus_valid,
    input wire bus_write,
    input wire [7:0] bus_addr,
    input wire [31:0] bus_wdata,
    input wire [3:0] bus_wstrb,
    output wire bus_ready,
    output wire [31:0] bus_rdata,
    input wire host_wr_valid,
    output wire host_wr_ready,
    input wire [63:0] host_wr_addr,
    input wire [127:0] host_wr_data,
    input wire [15:0] host_wr_strb,
    input wire host_load_start,
    input wire host_load_valid,
    input wire host_load_last,
    input wire [255:0] host_load_data,
    input wire [15:0] host_load_valid_elems,
    output wire host_load_ready,
    output wire host_loaded,
    output wire [31:0] host_loaded_k,
    input wire result_ready,
    output wire result_valid,
    output wire signed [31:0] partial_sum,
    output wire [15:0] result_row_id,
    output wire [15:0] result_group_id,
    output wire busy,
    output wire done,
    output wire error,
    output wire [7:0] error_code,
    output wire reader_done,
    output wire reader_busy,
    output wire [63:0] activation_base_cfg
);
    accelerator_control_top #(
        .MEMORY_LATENCY(MEMORY_LATENCY),
        .MEMORY_RANDOM_STALL(MEMORY_RANDOM_STALL),
        .CACHE_MAX_K(CACHE_MAX_K),
        .LANES(LANES)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .bus_valid(bus_valid), .bus_write(bus_write), .bus_addr(bus_addr),
        .bus_wdata(bus_wdata), .bus_wstrb(bus_wstrb), .bus_ready(bus_ready),
        .bus_rdata(bus_rdata),
        .host_wr_valid(host_wr_valid), .host_wr_ready(host_wr_ready),
        .host_wr_addr(host_wr_addr), .host_wr_data(host_wr_data),
        .host_wr_strb(host_wr_strb),
        .host_load_start(host_load_start), .host_load_valid(host_load_valid),
        .host_load_last(host_load_last), .host_load_data(host_load_data),
        .host_load_valid_elems(host_load_valid_elems),
        .host_load_ready(host_load_ready), .host_loaded(host_loaded),
        .host_loaded_k(host_loaded_k),
        .result_ready(result_ready), .result_valid(result_valid),
        .partial_sum(partial_sum), .result_row_id(result_row_id),
        .result_group_id(result_group_id), .busy(busy), .done(done),
        .error(error), .error_code(error_code), .reader_done(reader_done),
        .reader_busy(reader_busy), .activation_base_cfg(activation_base_cfg)
    );
endmodule
