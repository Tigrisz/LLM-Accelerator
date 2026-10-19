// System-control wrapper around the existing Task-B data path.
// Phase 1 deliberately keeps activation loading host-visible and synchronous;
// the saved activation_base register is reserved for the later DMA adapter.
module accelerator_control_top #(
    parameter integer MEMORY_LATENCY = 2,
    parameter integer MEMORY_RANDOM_STALL = 1,
    parameter integer CACHE_MAX_K = 8192,
    parameter integer LANES = 32
) (
    input wire         clk,
    input wire         rst_n,
    input wire         bus_valid,
    input wire         bus_write,
    input wire [7:0]   bus_addr,
    input wire [31:0]  bus_wdata,
    input wire [3:0]   bus_wstrb,
    output wire        bus_ready,
    output wire [31:0] bus_rdata,
    input wire         host_wr_valid,
    output wire        host_wr_ready,
    input wire [63:0]  host_wr_addr,
    input wire [127:0] host_wr_data,
    input wire [15:0]  host_wr_strb,
    input wire         host_load_start,
    input wire         host_load_valid,
    input wire         host_load_last,
    input wire [255:0] host_load_data,
    input wire [15:0]  host_load_valid_elems,
    output wire        host_load_ready,
    output wire        host_loaded,
    output wire [31:0] host_loaded_k,
    input wire         result_ready,
    output wire        result_valid,
    output wire signed [31:0] partial_sum,
    output wire [15:0] result_row_id,
    output wire [15:0] result_group_id,
    output wire        busy,
    output wire        done,
    output wire        error,
    output wire [7:0]  error_code,
    output wire        reader_done,
    output wire        reader_busy,
    output wire [63:0] activation_base_cfg
);
    wire [127:0] memory_data;
    wire memory_last, memory_error;
    wire rd_req_valid, rd_req_ready, rd_data_valid, rd_data_ready;
    wire [63:0] rd_addr;
    wire [31:0] rd_nbytes;
    wire reader_error;
    wire weight_valid, weight_ready, weight_first, weight_last;
    wire [127:0] weight_data;
    wire [15:0] weight_row, weight_group;
    wire activation_valid, activation_ready, activation_last;
    wire [255:0] activation_data;
    wire pair_valid, pair_ready, pair_first, pair_last;
    wire [127:0] pair_weight_data;
    wire [255:0] pair_activation_data;
    wire [15:0] pair_row_id, pair_group_id;
    wire compute_in_valid, compute_in_ready, compute_first, compute_last;
    wire [LANES*4-1:0] compute_weight_data;
    wire [LANES*8-1:0] compute_activation_data;
    wire [15:0] compute_row_id, compute_group_id;
    wire controller_reader_start, controller_cache_read_start;
    wire start_pulse, clear_status_pulse;
    wire [63:0] weight_base, activation_base;
    wire [15:0] n_rows;
    wire [31:0] k_elems;
    wire status_result_pending;
    wire [31:0] cycle_count, result_count;

    memory_model #(
        .LATENCY(MEMORY_LATENCY),
        .RANDOM_STALL(MEMORY_RANDOM_STALL)
    ) memory_inst (
        .clk(clk), .rst_n(rst_n),
        .wr_valid(host_wr_valid), .wr_ready(host_wr_ready),
        .wr_addr(host_wr_addr), .wr_data(host_wr_data), .wr_strb(host_wr_strb),
        .rd_req_valid(rd_req_valid), .rd_req_ready(rd_req_ready),
        .rd_addr(rd_addr), .rd_nbytes(rd_nbytes),
        .rd_data_valid(rd_data_valid), .rd_data_ready(rd_data_ready),
        .rd_data(memory_data), .rd_last(memory_last), .rd_error(memory_error)
    );

    weight_reader reader_inst (
        .clk(clk), .rst_n(rst_n), .start(controller_reader_start),
        .weight_base(weight_base), .n_rows(n_rows), .k_elems(k_elems),
        .busy(reader_busy), .done(reader_done), .error(reader_error),
        .rd_req_valid(rd_req_valid), .rd_req_ready(rd_req_ready),
        .rd_addr(rd_addr), .rd_nbytes(rd_nbytes),
        .rd_data_valid(rd_data_valid), .rd_data_ready(rd_data_ready),
        .rd_data(memory_data), .rd_last(memory_last), .rd_error(memory_error),
        .weight_valid(weight_valid), .weight_ready(weight_ready),
        .weight_data(weight_data), .group_first(weight_first),
        .group_last(weight_last), .row_id(weight_row), .group_id(weight_group)
    );

    activation_cache #(.MAX_K(CACHE_MAX_K)) cache_inst (
        .clk(clk), .rst_n(rst_n),
        .load_start(host_load_start), .load_valid(host_load_valid),
        .load_ready(host_load_ready), .load_data(host_load_data),
        .load_valid_elems(host_load_valid_elems), .load_last(host_load_last),
        .loaded(host_loaded), .loaded_k(host_loaded_k),
        .read_start(controller_cache_read_start),
        .read_valid(activation_valid), .read_ready(activation_ready),
        .read_data(activation_data), .read_last(activation_last)
    );

    paired_input_stream pair_inst (
        .weight_valid(weight_valid), .weight_ready(weight_ready),
        .weight_data(weight_data), .weight_group_first(weight_first),
        .weight_group_last(weight_last), .weight_row_id(weight_row),
        .weight_group_id(weight_group), .activation_valid(activation_valid),
        .activation_ready(activation_ready), .activation_data(activation_data),
        .in_valid(pair_valid), .in_ready(pair_ready),
        .in_weight_data(pair_weight_data), .in_activation_data(pair_activation_data),
        .in_group_first(pair_first), .in_group_last(pair_last),
        .in_row_id(pair_row_id), .in_group_id(pair_group_id)
    );

    generate
        if (LANES == 16) begin : gen_lane16
            lane_adapter_32_to_16 adapter_inst (
                .clk(clk), .rst_n(rst_n),
                .in_valid(pair_valid), .in_ready(pair_ready),
                .in_weight_data(pair_weight_data),
                .in_activation_data(pair_activation_data),
                .in_group_first(pair_first), .in_group_last(pair_last),
                .in_row_id(pair_row_id), .in_group_id(pair_group_id),
                .out_valid(compute_in_valid), .out_ready(compute_in_ready),
                .out_weight_data(compute_weight_data),
                .out_activation_data(compute_activation_data),
                .out_group_first(compute_first), .out_group_last(compute_last),
                .out_row_id(compute_row_id), .out_group_id(compute_group_id)
            );
        end else if (LANES == 32) begin : gen_lane32
            assign compute_in_valid = pair_valid;
            assign pair_ready = compute_in_ready;
            assign compute_weight_data = pair_weight_data;
            assign compute_activation_data = pair_activation_data;
            assign compute_first = pair_first;
            assign compute_last = pair_last;
            assign compute_row_id = pair_row_id;
            assign compute_group_id = pair_group_id;
        end else begin : gen_unsupported_lanes
            initial $error("accelerator_control_top supports LANES=16 or LANES=32");
            assign compute_in_valid = 1'b0;
            assign pair_ready = 1'b0;
            assign compute_weight_data = '0;
            assign compute_activation_data = '0;
            assign compute_first = 1'b0;
            assign compute_last = 1'b0;
            assign compute_row_id = 16'b0;
            assign compute_group_id = 16'b0;
        end
    endgenerate

    gemv_core #(.LANES(LANES)) core_inst (
        .clk(clk), .rst_n(rst_n), .in_valid(compute_in_valid), .in_ready(compute_in_ready),
        .weight_data(compute_weight_data), .activation_data(compute_activation_data),
        .group_first(compute_first), .group_last(compute_last), .row_id(compute_row_id),
        .group_id(compute_group_id), .out_valid(result_valid),
        .out_ready(result_ready), .partial_sum(partial_sum),
        .out_row_id(result_row_id), .out_group_id(result_group_id)
    );

    task_controller #(.CACHE_MAX_K(CACHE_MAX_K)) controller_inst (
        .clk(clk), .rst_n(rst_n), .start_request(start_pulse),
        .clear_status(clear_status_pulse), .n_rows(n_rows), .k_elems(k_elems),
        .cache_loaded(host_loaded), .cache_loaded_k(host_loaded_k),
        .reader_error(reader_error), .activation_valid(activation_valid),
        .activation_ready(activation_ready), .activation_last(activation_last),
        .result_valid(result_valid), .result_ready(result_ready),
        .reader_start(controller_reader_start),
        .cache_read_start(controller_cache_read_start), .busy(busy),
        .done(done), .error(error), .error_code(error_code),
        .cycle_count(cycle_count), .result_count(result_count),
        .result_pending(status_result_pending)
    );

    control_regs regs_inst (
        .clk(clk), .rst_n(rst_n), .bus_valid(bus_valid),
        .bus_write(bus_write), .bus_addr(bus_addr), .bus_wdata(bus_wdata),
        .bus_wstrb(bus_wstrb), .bus_ready(bus_ready), .bus_rdata(bus_rdata),
        .start_pulse(start_pulse), .clear_status_pulse(clear_status_pulse),
        .weight_base(weight_base), .activation_base(activation_base),
        .n_rows(n_rows), .k_elems(k_elems), .status_busy(busy),
        .status_done(done), .status_error(error),
        .status_act_loaded(host_loaded), .status_reader_done(reader_done),
        .status_result_pending(status_result_pending), .error_code(error_code),
        .cycle_count(cycle_count), .result_count(result_count)
    );

    // Expose the reserved activation base so the phase-1 lint boundary is
    // explicit and the later DMA adapter has a stable connection point.
    assign activation_base_cfg = activation_base;
endmodule
