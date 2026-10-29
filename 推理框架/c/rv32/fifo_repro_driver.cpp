#include "Vfifo_nba_repro.h"
#include "verilated.h"
#include <iostream>
int main(int argc,char**argv){
    Verilated::commandArgs(argc,argv);Vfifo_nba_repro dut;
    dut.clk=0;dut.consume=1;dut.pop=1;dut.remaining=1;dut.incoming_pc=8;
    dut.response[0]=0;dut.response[1]=0;dut.response[2]=0x10;
    dut.response_second[0]=0;dut.response_second[1]=0;dut.response_second[2]=0x50;
    dut.eval();dut.clk=1;dut.eval();
    std::cout<<"FIFO pc="<<dut.pc_one<<','<<dut.pc_two<<" meta="<<std::hex<<(unsigned)dut.meta_one<<','<<(unsigned)dut.meta_two<<'\n';
    bool passed=dut.pc_one==8&&dut.pc_two==12&&dut.meta_one==0x44&&dut.meta_two==0x46;
    dut.final();return passed?0:1;
}
