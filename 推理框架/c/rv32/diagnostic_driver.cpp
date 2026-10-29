// Diagnostic only: preserve firmware/RTL, record both retirement lanes in order.
#include "Vqinglong_soc.h"
#include "verilated.h"
#ifdef T4_PIPE_DIAG
#include "Vqinglong_soc___024root.h"
#define CPU(name) soc.rootp->qinglong_soc__DOT__cpu__DOT__##name
#endif
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>

int main(int argc,char **argv){
    if(argc!=3&&argc!=4)return 2;
    Verilated::commandArgs(argc,argv);Vqinglong_soc soc;
    uint64_t cycles=0,count=0,written=0,limit=std::strtoull(argv[1],nullptr,10);
    uint64_t trace_limit=argc==4?std::strtoull(argv[3],nullptr,10):600000;
    std::ofstream trace(argv[2]);if(!trace)return 2;
#ifdef T4_PIPE_DIAG
    std::ofstream pipe(std::string(argv[2])+".pipe");
#endif
    auto retire=[&](bool valid,uint32_t pc,uint32_t insn,uint32_t rd,uint32_t data,int lane){
        if(valid){uint64_t index=count++;if(index<trace_limit){trace<<std::dec<<index<<' '<<cycles<<' '<<lane<<' '<<std::hex<<pc<<' '<<insn<<' '<<rd<<' '<<data<<'\n';if(trace)written++;}}
    };
    soc.clk=0;soc.rst=1;soc.irq_external=0;soc.eval();
    for(;cycles<limit&&!soc.done&&!Verilated::gotFinish();cycles++){
        soc.clk=0;soc.rst=cycles<6;soc.eval();
#ifdef T4_PIPE_DIAG
        if(!soc.rst&&cycles<2000){
            pipe<<std::dec<<cycles<<std::hex<<" F "<<CPU(fetch_pc)[0]<<' '<<CPU(fetch_insn)[0]<<' '<<(unsigned)CPU(fetch_meta)[0]
                <<' '<<CPU(fetch_pc)[1]<<' '<<CPU(fetch_insn)[1]<<' '<<(unsigned)CPU(fetch_meta)[1]
                <<" PAIR "<<(unsigned)CPU(id_issue)<<' '<<(unsigned)CPU(pair_normal)<<' '<<(unsigned)CPU(pair_swapped)
                <<" X "<<CPU(x_pc)<<' '<<CPU(x_insn)<<' '<<CPU(x_a)<<' '<<CPU(x_second_a)<<' '<<CPU(a_second)
                <<" M "<<CPU(m_pc)<<' '<<(unsigned)CPU(m_rd)<<' '<<CPU(m_result)<<' '<<(unsigned)CPU(m_second_rd)<<' '<<CPU(m_second_result)
                <<'\n';
        }
#endif
        soc.clk=1;soc.eval();
        if(soc.rst)continue;
        retire(soc.retire_valid,soc.retire_pc,soc.retire_insn,soc.retire_rd,soc.retire_data,0);
        retire(soc.retire_second_valid,soc.retire_second_pc,soc.retire_second_insn,soc.retire_second_rd,soc.retire_second_data,1);
        if(soc.console_valid)std::cout<<static_cast<char>(soc.console_data);
        if(soc.trap_valid)std::cout<<"TRAP="<<std::hex<<soc.trap_pc<<','<<soc.trap_cause<<','<<soc.trap_value<<'\n';
    }
    trace.flush();bool trace_good=trace.good();trace.close();
    if(!trace_good||trace.fail()){std::cerr<<"Trace write/flush/close failed\n";soc.final();return 2;}
    std::cout<<"DONE="<<(unsigned)soc.done<<" EXIT="<<std::dec<<soc.exit_code<<" CYCLES="<<cycles<<" RETIRED="<<count
             <<" TRACE_ROWS="<<written<<'\n';
    soc.final();return soc.done&&soc.exit_code==0?0:1;
}
