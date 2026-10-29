module fifo_repro_tb;
    logic clk=0;
    logic consume=1;
    logic [1:0] pop=1;
    logic [2:0] remaining=1;
    logic [31:0] incoming_pc=8;
    logic [86:0] response,response_second;
    wire [31:0] pc_one,pc_two;wire [6:0] meta_one,meta_two;
    fifo_nba_repro dut(.*);
    initial begin
        response=87'h10<<64;response_second=87'h50<<64;
        #1;clk=1;#1;
        $display("FIFO pc=%0d,%0d meta=%h,%h",pc_one,pc_two,meta_one,meta_two);
        if(pc_one!=8||pc_two!=12||meta_one!='h44||meta_two!='h46)$fatal(1,"FIFO payload and metadata diverged");
        $finish;
    end
endmodule
