// Reduced FIFO scheduling reproducer; runtime inputs prevent constant folding.
module fifo_nba_repro(
    input logic clk,consume,
    input logic [1:0] pop,
    input logic [2:0] remaining,
    input logic [31:0] incoming_pc,
    input logic [86:0] response,response_second,
    output wire [31:0] pc_one,pc_two,
    output wire [6:0] meta_one,meta_two
);
    import rv32_pkg::*;
    logic [31:0] pc[0:3];
    logic [6:0] meta[0:3];
    integer fi;
    function automatic [6:0] issue_metadata(input logic [86:0] bits_in);
        decode_t d;
        begin
        d=bits_in;
        issue_metadata={
            !d.illegal&&!d.serial&&d.reg_write&&d.alu<=ALU_COPY&&
            !(d.load||d.store||d.mul||d.div||d.branch||d.jal||d.jalr),
            d.illegal,d.serial,(d.branch||d.jal||d.jalr),
            d.reg_write,d.use_rs1,d.use_rs2};
        end
    endfunction
    assign pc_one=pc[1];assign pc_two=pc[2];assign meta_one=meta[1];assign meta_two=meta[2];
    always_ff @(posedge clk) begin
        for(fi=0;fi<4;fi=fi+1)begin
            if(pop==1&&fi<3)begin pc[fi]<=pc[fi+1];meta[fi]<=meta[fi+1];end
            else if(pop==2&&fi<2)begin pc[fi]<=pc[fi+2];meta[fi]<=meta[fi+2];end
            if(consume)begin
                if(remaining==fi[2:0])begin pc[fi]<=incoming_pc;meta[fi]<=issue_metadata(response);end
                if(remaining+3'd1==fi[2:0])begin pc[fi]<=incoming_pc+4;meta[fi]<=issue_metadata(response_second);end
            end
        end
    end
    initial begin
        pc[0]=0;pc[1]=4;pc[2]=0;pc[3]=0;
        meta[0]='h44;meta[1]='h46;meta[2]=0;meta[3]=0;
    end
endmodule
