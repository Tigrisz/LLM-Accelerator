// Verilator driver for the pinned QingLong CPU/SoC RTL; no ISA emulation here.
#include "Vqinglong_soc.h"
#include "verilated.h"
#include <cstdint>
#include <cstdlib>
#include <iostream>

int main(int argc,char **argv){
    Verilated::commandArgs(argc,argv);Vqinglong_soc soc;
    uint64_t cycles=0,limit=20000000;uint32_t min_sp=0x10000,traps=0,violations=0;bool stack_started=false;
    if(argc>1)limit=std::strtoull(argv[1],nullptr,10);
    soc.clk=0;soc.rst=1;soc.irq_external=0;soc.eval();
    auto stack=[&](bool valid,uint32_t rd,uint32_t value){
        if(!valid||rd!=2)return;
        if(!stack_started){if(value==0x10000)stack_started=true;else return;}
        if(value<min_sp)min_sp=value;
        if(value<0xe000||value>0x10000||(value&15u))violations++;
    };
    for(;cycles<limit&&!soc.done&&!Verilated::gotFinish();cycles++){
        soc.clk=0;soc.rst=cycles<6;soc.eval();
        soc.clk=1;soc.eval();
        if(soc.rst)continue;
        if(soc.console_valid)std::cout<<static_cast<char>(soc.console_data);
        stack(soc.retire_valid,soc.retire_rd,soc.retire_data);
        stack(soc.retire_second_valid,soc.retire_second_rd,soc.retire_second_data);
        if(soc.trap_valid){traps++;std::cout<<"TRAP_PC="<<std::hex<<soc.trap_pc<<"\nTRAP_CAUSE="<<soc.trap_cause<<"\n"<<std::dec;}
    }
    std::cout<<"RTL_DONE="<<(soc.done?1:0)<<"\nRTL_EXIT="<<soc.exit_code<<"\nRTL_CYCLES="<<cycles
             <<"\nRTL_MIN_SP="<<min_sp<<"\nRTL_STACK_VIOLATIONS="<<violations<<"\nRTL_TRAPS="<<traps
             <<"\nRTL_STACK_STARTED="<<(stack_started?1:0)<<"\n";
    soc.final();return soc.done&&soc.exit_code==0&&traps==0&&violations==0&&stack_started?0:1;
}
