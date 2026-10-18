#include "Vtb_b_integration.h"
#include "verilated.h"
#include "verilated_vcd_c.h"
#include "vector_case.h"
#include "stream_monitor.h"
#include <array>
#include <iostream>
#include <random>
#include <cstdlib>
#include <stdexcept>

class Integration {
public:
    Vtb_b_integration dut;
    VerilatedVcdC trace;
    bool tracing=false, verify=false;
    const VectorCase* data=nullptr;
    uint64_t cycles=0, time=0, bytes=0, input_wait=0, output_wait=0;
    int beats=0, outputs=0, requests=0;
    std::string scenario="initial";
    StreamMonitor<std::array<uint32_t,16>> input_monitor{"paired input"};
    StreamMonitor<std::array<uint32_t,3>> output_monitor{"integration output"};
    GroupMonitor group_monitor{32};
    Integration() {
        if(const char* path=std::getenv("TRACE_FILE")) {
            Verilated::traceEverOn(true); dut.trace(&trace,99); trace.open(path); tracing=true;
        }
        dut.clk=0; dut.rst_n=1; dut.start=0; dut.wr_valid=0; dut.load_start=0;
        dut.load_valid=0; dut.load_last=0; dut.load_valid_elems=0; dut.out_ready=0;
        dut.n_rows=0; dut.k_elems=0; dut.weight_base=256; dut.wr_addr=0; dut.wr_strb=0xffff;
        for(int i=0;i<4;i++) dut.wr_data[i]=0;
        for(int i=0;i<8;i++) dut.load_data[i]=0;
    }
    ~Integration() { dut.final(); if(tracing) trace.close(); }
    void eval() { dut.eval(); if(tracing) trace.dump(time++); }
    void check(bool ok,const char* msg) {
        if(!ok) throw std::runtime_error(scenario+": "+msg+" cycle="+std::to_string(cycles));
    }
    void reset() {
        verify=false; dut.clk=0; dut.rst_n=0; dut.start=0; dut.wr_valid=0;
        dut.load_valid=0; dut.load_start=0; dut.out_ready=0; eval();
        check(!dut.out_valid && !dut.dbg_in_valid && !dut.dbg_mem_valid && !dut.done,"reset retained valid/done");
        dut.clk=1; eval(); dut.clk=0; eval(); dut.rst_n=1; eval();
        input_monitor.reset(); output_monitor.reset(); group_monitor.reset();
    }
    void tick() {
        dut.clk=0; eval();
        bool hold=dut.out_valid && !dut.out_ready;
        auto ps=dut.partial_sum; auto row=dut.out_row_id; auto group=dut.out_group_id;
        bool in_hold=dut.dbg_in_valid && !dut.dbg_in_ready;
        std::array<uint32_t,4> iw{}; std::array<uint32_t,8> ix{};
        for(int i=0;i<4;i++) iw[i]=dut.dbg_weight[i];
        for(int i=0;i<8;i++) ix[i]=dut.dbg_activation[i];
        unsigned ir=dut.dbg_row, ig=dut.dbg_group, iff=dut.dbg_first, il=dut.dbg_last;
        std::array<uint32_t,16> payload{};
        for(int i=0;i<4;i++) payload[i]=iw[i];
        for(int i=0;i<8;i++) payload[i+4]=ix[i];
        payload[12]=ir; payload[13]=ig; payload[14]=iff; payload[15]=il;
        try {
            input_monitor.sample(dut.dbg_in_valid,dut.dbg_in_ready,payload);
            output_monitor.sample(dut.out_valid,dut.out_ready,{{ps,row,group}});
            group_monitor.sample(dut.dbg_in_valid && dut.dbg_in_ready,iff,il,ir,ig);
        } catch(const std::exception& e) { check(false,e.what()); }
        if(verify) {
            check(!dut.error,"reader reported error");
            check(!dut.out_valid || outputs < beats/4,"output valid before completed input group");
            if(dut.dbg_req_valid && dut.dbg_req_ready) {
                check(dut.dbg_addr==dut.weight_base+uint64_t(requests)*64 && dut.dbg_nbytes==64,"request address/length");
                ++requests;
            }
            if(dut.dbg_mem_valid && dut.dbg_mem_ready) { check(!dut.dbg_mem_error,"memory error"); bytes+=16; }
            if(dut.dbg_in_valid && dut.dbg_in_ready) {
                int per_row=data->padded/32, r=beats/per_row, col=(beats%per_row)*32;
                check(r<data->n,"extra input beat");
                check(dut.dbg_row==r && dut.dbg_group==col/128 &&
                      dut.dbg_first==(col%128==0) && dut.dbg_last==(col%128==96),"input metadata");
                for(int i=0;i<32;i++) {
                    int w=(dut.dbg_weight[i/8]>>(4*(i%8)))&15;
                    int x=(dut.dbg_activation[i/4]>>(8*(i%4)))&255;
                    check(w==(data->w(r,col+i)&15) && x==data->activations[col+i],"paired payload mismatch");
                }
                ++beats;
            }
            if(dut.out_valid && dut.out_ready) {
                check(outputs<int(data->expected.size()),"duplicate output");
                check(dut.out_row_id==outputs/(data->padded/128) &&
                      dut.out_group_id==outputs%(data->padded/128) &&
                      int32_t(dut.partial_sum)==data->expected[outputs],"B golden result/tag mismatch");
                ++outputs;
            }
            if(!dut.dbg_in_valid) ++input_wait;
            if(hold) ++output_wait;
        }
        dut.clk=1; eval();
        if(hold) check(dut.out_valid && dut.partial_sum==ps && dut.out_row_id==row && dut.out_group_id==group,"unstable output");
        if(in_hold) {
            check(dut.dbg_in_valid && dut.dbg_row==ir && dut.dbg_group==ig && dut.dbg_first==iff && dut.dbg_last==il,"unstable input metadata");
            for(int i=0;i<4;i++) check(dut.dbg_weight[i]==iw[i],"unstable weight");
            for(int i=0;i<8;i++) check(dut.dbg_activation[i]==ix[i],"unstable activation");
        }
        if(verify && dut.done) check(outputs==int(data->expected.size()),"done before final output accepted");
        dut.clk=0; eval(); ++cycles;
    }
    void prepare(const VectorCase& c) {
        verify=false; data=&c; dut.n_rows=c.n; dut.k_elems=c.k; dut.weight_base=256;
        dut.out_ready=0; dut.start=0;
        for(size_t pos=0;pos<c.weights.size();pos+=16) {
            dut.wr_valid=1; dut.wr_addr=dut.weight_base+pos;
            for(int word=0;word<4;word++) {
                uint32_t value=0; for(int j=0;j<4;j++) value|=uint32_t(c.weights[pos+word*4+j])<<(8*j);
                dut.wr_data[word]=value;
            }
            eval(); check(dut.wr_ready,"memory not ready for preload"); tick();
        }
        dut.wr_valid=0; dut.load_start=1; tick(); dut.load_start=0;
        for(int pos=0;pos<c.padded;pos+=32) {
            dut.load_valid=1; dut.load_last=pos+32==c.padded;
            dut.load_valid_elems=std::max(0,std::min(32,c.k-pos));
            for(int word=0;word<8;word++) {
                uint32_t value=0; for(int j=0;j<4;j++) value|=uint32_t(c.activations[pos+word*4+j])<<(8*j);
                dut.load_data[word]=value;
            }
            eval(); check(dut.load_ready,"cache not ready for valid preload"); tick();
        }
        dut.load_valid=0; dut.load_last=0;
        check(dut.loaded && dut.loaded_k==unsigned(c.k),"cache logical length");
        beats=0; outputs=0; requests=0; bytes=0; input_wait=0; output_wait=0;
        dut.start=1; tick(); dut.start=0; verify=true;
    }
    void run(const VectorCase& c,int seed,bool stalls,bool final_hold) {
        scenario="integration N="+std::to_string(c.n)+" K="+std::to_string(c.k)+" seed="+std::to_string(seed);
        prepare(c); uint64_t begin=cycles; std::mt19937 rng(seed); int held=0;
        while(!dut.done) {
            check(cycles-begin<200000,"integration timeout");
            dut.out_ready=!stalls || rng()%3!=0;
            if(final_hold && dut.out_valid && outputs==int(c.expected.size())-1 && held<20) {
                dut.out_ready=0; ++held; check(!dut.done,"premature done");
            }
            tick();
        }
        check(beats==c.n*c.padded/32 && requests==c.n*c.padded/128 && bytes==c.weights.size(),"transfer counts");
        check(!final_hold || held==20,"final stall not exercised");
        auto measured_input_wait=input_wait, measured_output_wait=output_wait;
        for(int i=0;i<4;i++) tick();
        check(!dut.busy,"reader not idle after completion"); verify=false;
        std::cout<<"PASS INTEGRATION N="<<c.n<<" K="<<c.k<<" seed="<<seed
                 <<" random_output_stalls="<<stalls<<" final_hold="<<held<<" cycles="<<cycles-begin-4<<" weight_bytes="<<bytes
                 <<" groups="<<outputs<<" input_wait="<<measured_input_wait<<" output_wait="<<measured_output_wait<<'\n';
    }
    void capacity() {
        reset(); dut.load_start=1; tick(); dut.load_start=0;
        dut.load_valid=1; dut.load_last=0; dut.load_valid_elems=32;
        for(int b=0;b<8192/32;b++) { eval(); check(dut.load_ready,"cache rejects in-range beat"); tick(); }
        eval(); check(!dut.load_ready,"cache accepts beyond MAX_K"); dut.load_valid=0;
        std::cout<<"PASS CACHE_CAPACITY MAX_K=8192\n";
    }
    void invalid_request(uint64_t base,int n,int k) {
        reset(); dut.weight_base=base; dut.n_rows=n; dut.k_elems=k;
        // No activations: error completion must not depend on activation_valid.
        dut.start=1; tick(); dut.start=0;
        for(int i=0;i<100;i++) tick();
        check(dut.error && !dut.done && !dut.out_valid,"invalid config not reported");
        check(dut.dbg_req_ready && !dut.dbg_mem_valid,"error response not drained");
        std::cout<<"PASS ERROR base="<<base<<" N="<<n<<" K="<<k<<'\n';
    }
    void reset_cases(const VectorCase& c) {
        prepare(c); dut.out_ready=1;
        for(int i=0;beats<2 && i<1000;i++) tick();
        check(beats==2,"partial reset setup"); reset(); run(c,77,true,true);
        prepare(c); dut.out_ready=0;
        for(int i=0;!dut.out_valid && i<1000;i++) tick();
        check(dut.out_valid,"pending reset setup"); reset(); run(c,78,true,true);
        std::cout<<"PASS RESET partial_group,pending_output,restart\n";
    }
};
int main(int argc,char** argv) {
    Verilated::commandArgs(argc,argv);
    try {
        Integration test; test.reset();
        if(argc==2 && std::string(argv[1])=="--capacity") test.capacity();
        else if(argc==2 && std::string(argv[1])=="--errors") {
            test.invalid_request(3,1,128); test.invalid_request(65520,1,128);
            test.invalid_request(256,0,128); test.invalid_request(256,1,0);
        } else if(argc>=2) {
            VectorCase c(argv[1]);
            if(argc==3 && std::string(argv[2])=="--reset") test.reset_cases(c);
            else { test.run(c,42,false,true); test.run(c,43,true,true); }
        } else throw std::runtime_error("usage: integration case.txt [--reset] | --capacity | --errors");
    } catch(const std::exception& e) { std::cerr<<"FAIL "<<e.what()<<'\n'; return 1; }
}
