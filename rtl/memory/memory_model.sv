// Abstract single-outstanding 128-bit read memory for Day 5 simulation.
// It intentionally has no AXI/DDR dependency. Replace this module with a
// DDR adapter after the RISC-V/board interface is available.
module memory_model #(
    parameter integer ADDR_WIDTH = 64,
    parameter integer MEM_BYTES = 65536,
    parameter integer DATA_WIDTH = 128,
    parameter integer LATENCY = 2,
    parameter integer RANDOM_STALL = 0
) (
    input  logic                     clk,
    input  logic                     rst_n,

    input  logic                     wr_valid,
    output logic                     wr_ready,
    input  logic [ADDR_WIDTH-1:0]    wr_addr,
    input  logic [DATA_WIDTH-1:0]    wr_data,
    input  logic [DATA_WIDTH/8-1:0]  wr_strb,

    input  logic                     rd_req_valid,
    output logic                     rd_req_ready,
    input  logic [ADDR_WIDTH-1:0]    rd_addr,
    input  logic [31:0]              rd_nbytes,

    output logic                     rd_data_valid,
    input  logic                     rd_data_ready,
    output logic [DATA_WIDTH-1:0]    rd_data,
    output logic                     rd_last,
    output logic                     rd_error
);
    localparam integer DATA_BYTES = DATA_WIDTH / 8;
    localparam integer MEM_ADDR_WIDTH = (MEM_BYTES <= 2) ? 1 : $clog2(MEM_BYTES);

    typedef enum logic [1:0] {S_IDLE, S_WAIT, S_SEND} state_t;
    state_t state;

    logic [7:0] mem [0:MEM_BYTES-1];
    logic [ADDR_WIDTH-1:0] current_addr;
    logic [31:0] beats_left;
    logic [31:0] wait_left;
    logic [DATA_WIDTH-1:0] data_reg;
    logic last_reg;
    logic error_reg;
    logic valid_reg;
    logic [15:0] lfsr;
    integer i;

    function automatic logic request_in_range(
        input logic [ADDR_WIDTH-1:0] address,
        input logic [31:0] byte_count
    );
        logic [ADDR_WIDTH:0] end_address;
        begin
            end_address = {1'b0, address} + byte_count;
            request_in_range = (address < MEM_BYTES) &&
                               (byte_count != 0) &&
                               ((address % DATA_BYTES) == 0) &&
                               ((byte_count % DATA_BYTES) == 0) &&
                               (end_address <= MEM_BYTES);
        end
    endfunction

    function automatic logic should_stall;
        begin
            should_stall = (RANDOM_STALL != 0) && lfsr[0];
        end
    endfunction

    assign rd_req_ready = (state == S_IDLE);
    assign wr_ready = (state == S_IDLE);
    assign rd_data_valid = valid_reg;
    assign rd_data = data_reg;
    assign rd_last = last_reg;
    assign rd_error = error_reg;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_IDLE;
            current_addr <= '0;
            beats_left <= '0;
            wait_left <= '0;
            data_reg <= '0;
            last_reg <= 1'b0;
            error_reg <= 1'b0;
            valid_reg <= 1'b0;
            lfsr <= 16'h1;
        end else begin
            // A tiny deterministic LFSR makes backpressure reproducible.
            lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};

            if (wr_valid && wr_ready) begin
                for (i = 0; i < DATA_BYTES; i = i + 1) begin
                    if (wr_strb[i] && ((wr_addr + i) < MEM_BYTES)) begin
                        mem[wr_addr + i] <= wr_data[i*8 +: 8];
                    end
                end
            end

            case (state)
                S_IDLE: begin
                    valid_reg <= 1'b0;
                    error_reg <= 1'b0;
                    last_reg <= 1'b0;
                    if (rd_req_valid && rd_req_ready) begin
                        current_addr <= rd_addr;
                        beats_left <= (rd_nbytes + DATA_BYTES - 1) / DATA_BYTES;
                        wait_left <= LATENCY;
                        error_reg <= !request_in_range(rd_addr, rd_nbytes);
                        state <= S_WAIT;
                    end
                end

                S_WAIT: begin
                    if (wait_left != 0) begin
                        wait_left <= wait_left - 1;
                    end else if (!valid_reg && !should_stall()) begin
                        data_reg <= '0;
                        if (error_reg) begin
                            last_reg <= 1'b1;
                        end else begin
                            for (i = 0; i < DATA_BYTES; i = i + 1) begin
                                if ((current_addr + i) < MEM_BYTES) begin
                                    data_reg[i*8 +: 8] <= mem[current_addr + i];
                                end
                            end
                            last_reg <= (beats_left == 1);
                        end
                        valid_reg <= 1'b1;
                        state <= S_SEND;
                    end
                end

                S_SEND: begin
                    if (valid_reg && rd_data_ready) begin
                        valid_reg <= 1'b0;
                        if (error_reg || (beats_left <= 1)) begin
                            state <= S_IDLE;
                            beats_left <= '0;
                        end else begin
                            current_addr <= current_addr + DATA_BYTES;
                            beats_left <= beats_left - 1;
                            state <= S_WAIT;
                        end
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end
endmodule

