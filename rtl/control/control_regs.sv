// Small internal control/status register block.
// The bus is intentionally generic: one valid transfer per cycle, with a
// one-cycle write side effect. An AXI-Lite/Wishbone adapter can be added later.
module control_regs #(
    parameter integer ADDR_WIDTH = 8
) (
    input  wire                 clk,
    input  wire                 rst_n,
    input  wire                 bus_valid,
    input  wire                 bus_write,
    input  wire [ADDR_WIDTH-1:0] bus_addr,
    input  wire [31:0]           bus_wdata,
    input  wire [3:0]            bus_wstrb,
    output wire                  bus_ready,
    output reg  [31:0]           bus_rdata,
    output reg                   start_pulse,
    output reg                   clear_status_pulse,
    output reg  [63:0]           weight_base,
    output reg  [63:0]           activation_base,
    output reg  [15:0]           n_rows,
    output reg  [31:0]           k_elems,
    input  wire                  status_busy,
    input  wire                  status_done,
    input  wire                  status_error,
    input  wire                  status_act_loaded,
    input  wire                  status_reader_done,
    input  wire                  status_result_pending,
    input  wire [7:0]            error_code,
    input  wire [31:0]           cycle_count,
    input  wire [31:0]           result_count
);
    localparam [7:0] ADDR_CTRL         = 8'h00;
    localparam [7:0] ADDR_STATUS       = 8'h04;
    localparam [7:0] ADDR_WEIGHT_LO    = 8'h08;
    localparam [7:0] ADDR_WEIGHT_HI    = 8'h0c;
    localparam [7:0] ADDR_ACT_LO       = 8'h10;
    localparam [7:0] ADDR_ACT_HI       = 8'h14;
    localparam [7:0] ADDR_N_ROWS       = 8'h18;
    localparam [7:0] ADDR_K_ELEMS      = 8'h1c;
    localparam [7:0] ADDR_ERROR_CODE   = 8'h20;
    localparam [7:0] ADDR_CYCLE_COUNT  = 8'h24;
    localparam [7:0] ADDR_RESULT_COUNT = 8'h28;

    assign bus_ready = rst_n;

    always @* begin
        bus_rdata = 32'b0;
        case (bus_addr)
            ADDR_STATUS: begin
                bus_rdata[0] = status_busy;
                bus_rdata[1] = status_done;
                bus_rdata[2] = status_error;
                bus_rdata[3] = status_act_loaded;
                bus_rdata[4] = status_reader_done;
                bus_rdata[5] = status_result_pending;
            end
            ADDR_WEIGHT_LO:    bus_rdata = weight_base[31:0];
            ADDR_WEIGHT_HI:    bus_rdata = weight_base[63:32];
            ADDR_ACT_LO:       bus_rdata = activation_base[31:0];
            ADDR_ACT_HI:       bus_rdata = activation_base[63:32];
            ADDR_N_ROWS:       bus_rdata = {16'b0, n_rows};
            ADDR_K_ELEMS:      bus_rdata = k_elems;
            ADDR_ERROR_CODE:   bus_rdata = {24'b0, error_code};
            ADDR_CYCLE_COUNT:  bus_rdata = cycle_count;
            ADDR_RESULT_COUNT: bus_rdata = result_count;
            default:           bus_rdata = 32'b0;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            start_pulse       <= 1'b0;
            clear_status_pulse <= 1'b0;
            weight_base      <= 64'b0;
            activation_base  <= 64'b0;
            n_rows           <= 16'b0;
            k_elems          <= 32'b0;
        end else begin
            start_pulse        <= 1'b0;
            clear_status_pulse <= 1'b0;
            if (bus_valid && bus_write && bus_ready && (bus_wstrb != 4'b0)) begin
                case (bus_addr)
                    ADDR_CTRL: begin
                        if (bus_wdata[0]) start_pulse <= 1'b1;
                        if (bus_wdata[1]) clear_status_pulse <= 1'b1;
                    end
                    ADDR_WEIGHT_LO: weight_base[31:0] <= bus_wdata;
                    ADDR_WEIGHT_HI: weight_base[63:32] <= bus_wdata;
                    ADDR_ACT_LO:    activation_base[31:0] <= bus_wdata;
                    ADDR_ACT_HI:    activation_base[63:32] <= bus_wdata;
                    ADDR_N_ROWS:    n_rows <= bus_wdata[15:0];
                    ADDR_K_ELEMS:   k_elems <= bus_wdata;
                    default: begin end
                endcase
            end
        end
    end
endmodule
