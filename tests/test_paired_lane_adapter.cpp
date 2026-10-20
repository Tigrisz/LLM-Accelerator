#include "Vpaired_lane_adapter.h"
#include "verilated.h"
#include "verilated_vcd_c.h"
#include "stream_monitor.h"
#include <array>
#include <cstdlib>
#include <iostream>
#include <random>
#include <stdexcept>

class Test {
    Vpaired_lane_adapter d;
    VerilatedVcdC trace;
    bool tracing=false;
    uint64_t time=0;
    int sent=0, received=0, salt=0;
    StreamMonitor<std::array<uint32_t,10>> monitor{"adapter output"};
    static uint32_t word(int beat,int index,int salt) {
        return uint32_t(beat+salt)*0x9e3779b9u ^ uint32_t(index+1)*0x13579bdfu;
    }
    void check(bool ok,const char* message) {
        if(!ok) throw std::runtime_error(std::string(message)+" sent="+std::to_string(sent)+" received="+std::to_string(received));
    }
    void eval() { d.eval(); if(tracing) trace.dump(time++); }
public:
    Test() {
        if(const char* path=std::getenv("TRACE_FILE")) {
            Verilated::traceEverOn(true); d.trace(&trace,99); trace.open(path); tracing=true;
        }
        d.clk=0; d.rst_n=1; d.s_valid=0; d.m_ready=0;
    }
    ~Test() { d.final(); if(tracing) trace.close(); }
    void reset() {
        d.rst_n=0; eval(); check(!d.m_valid && !d.s_ready,"reset handshake");
        d.clk=1; eval(); d.clk=0; eval(); d.rst_n=1;
        sent=received=0; salt+=17; monitor.reset();
    }
    void tick(bool valid,bool ready) {
        d.s_valid=valid; d.m_ready=ready;
        // Invalid source cycles deliberately contain unrelated data/metadata.
        int b=valid ? sent : sent+777;
        for(int i=0;i<4;i++) d.s_weight[i]=word(b,i,salt);
        for(int i=0;i<8;i++) d.s_activation[i]=word(b,i+4,salt);
        d.s_first=(b%4==0); d.s_last=(b%4==3);
        d.s_row=b/12; d.s_group=(b/4)%3;
        d.clk=0; eval();
        std::array<uint32_t,10> payload{};
        payload[0]=uint32_t(d.m_weight); payload[1]=uint32_t(d.m_weight>>32);
        for(int i=0;i<4;i++) payload[i+2]=d.m_activation[i];
        payload[6]=d.m_first; payload[7]=d.m_last; payload[8]=d.m_row; payload[9]=d.m_group;
        monitor.sample(d.m_valid,d.m_ready,payload);
        bool take_s=d.s_valid && d.s_ready;
        if(d.m_valid && d.m_ready) {
            int beat=received/2, half=received%2;
            check(payload[0]==word(beat,half*2,salt) && payload[1]==word(beat,half*2+1,salt),"weight ordering");
            for(int i=0;i<4;i++) check(payload[i+2]==word(beat,4+half*4+i,salt),"activation ordering");
            check(d.m_first==(beat%4==0 && half==0) && d.m_last==(beat%4==3 && half==1),"group markers");
            check(d.m_row==beat/12 && d.m_group==(beat/4)%3,"tags");
            check(take_s==(half==1),"upstream retired before both halves");
            ++received;
        } else check(!take_s,"source consumed without output");
        if(take_s) ++sent;
        d.clk=1; eval(); d.clk=0; eval();
    }
    void run() {
        for(int half=0;half<2;half++) {
            reset(); if(half) tick(true,true);
            for(int i=0;i<513;i++) tick(true,false);
            tick(true,true);
            if(!half) tick(true,true);
            check(sent==1 && received==2,"long stall loss/duplication");
        }
        // Reset at both split positions, with downstream blocked.
        for(int half=0;half<2;half++) {
            reset(); if(half) tick(true,true); tick(true,false);
            reset(); tick(true,true); tick(true,true);
            check(sent==1 && received==2,"reset did not restart low half");
        }
        for(int seed=0;seed<20;seed++) {
            reset(); std::mt19937 rng(seed); bool pending=false;
            for(int cycle=0;sent<256 && cycle<10000;cycle++) {
                if(!pending) pending=rng()%4!=0;
                int before=sent; tick(pending,rng()%3!=0);
                if(sent!=before) pending=false;
            }
            check(sent==256 && received==512,"random timeout/count");
        }
        reset(); for(int i=0;i<257;i++) tick(false,true);
        tick(true,true); tick(true,true);
        std::cout<<"PASS ADAPTER seeds=20 source_beats=5120 long_stall_each_half=513 reset_each_half idle_gap=257\n";
    }
};
int main(int argc,char** argv) {
    Verilated::commandArgs(argc,argv);
    try { Test t; t.run(); }
    catch(const std::exception& e) { std::cerr<<"FAIL "<<e.what()<<'\n'; return 1; }
}
