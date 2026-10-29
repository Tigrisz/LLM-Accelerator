module icarus_driver;
    parameter bit DUAL=1;
    parameter integer LIMIT=2000, TRACE=1;
    logic clk=0,rst=1;
    wire done,retire_valid,retire_second_valid,trap_valid;
    wire [31:0] exit_code,retire_pc,retire_insn,retire_data,retire_second_pc,retire_second_insn,retire_second_data,trap_pc,trap_cause,trap_value;
    wire [4:0] retire_rd,retire_second_rd;
    wire console_valid;wire [7:0] console_data;
    integer cycle;
    qinglong_soc #(.RAM_WORDS(16384),.INIT_FILE("firmware.hex"),.SIM_FAST_UART(1),.DUAL_ISSUE(DUAL)) dut(
        .clk(clk),.rst(rst),.irq_external(1'b0),.done(done),.exit_code(exit_code),
        .console_valid(console_valid),.console_data(console_data),
        .retire_valid(retire_valid),.retire_pc(retire_pc),.retire_insn(retire_insn),.retire_data(retire_data),.retire_rd(retire_rd),
        .retire_second_valid(retire_second_valid),.retire_second_pc(retire_second_pc),.retire_second_insn(retire_second_insn),.retire_second_data(retire_second_data),.retire_second_rd(retire_second_rd),
        .trap_valid(trap_valid),.trap_pc(trap_pc),.trap_cause(trap_cause),.trap_value(trap_value));
    initial begin
        for(cycle=0;cycle<LIMIT;cycle=cycle+1)begin
            #1;clk=0;rst=cycle<6;#1;clk=1;#1;
            if(!rst)begin
                if(TRACE&&retire_valid)$display("RET %h %h %d %h",retire_pc,retire_insn,retire_rd,retire_data);
                if(TRACE&&retire_second_valid)$display("RET %h %h %d %h",retire_second_pc,retire_second_insn,retire_second_rd,retire_second_data);
                if(console_valid)$write("%c",console_data);
                if(trap_valid)$fatal(1,"TRAP %h %h %h",trap_pc,trap_cause,trap_value);
                if(done)begin
                    $display("DONE exit=%0d cycles=%0d",exit_code,cycle+1);
                    if(exit_code!=0)$fatal(1,"Nonzero target exit");
                    $finish;
                end
            end
        end
        $fatal(1,"Watchdog");
    end
endmodule
