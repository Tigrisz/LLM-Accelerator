#include "Vgemv_core.h"
#include "verilated.h"
#include "verilated_vcd_c.h"
#include <array>
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
#include "vector_case.h"
#ifndef TEST_LANES
#define TEST_LANES 32
#endif

struct Result { int row, group; int32_t sum; };
struct Beat {
    std::array<int, TEST_LANES> w{}, x{};
    int row=0, group=0;
    bool first=false, last=false;
};
static uint64_t sim_time = 0;
class Test {
public:
    Vgemv_core dut;
    VerilatedVcdC trace;
    bool tracing=false;
    uint64_t cycles=0, accepted=0, received=0, input_idle=0, output_stall=0;
    std::deque<Result> expected;
    int32_t ref_sum=0;
    int beat_count=0, current_row=0, current_group=0;
    bool active=false;
    uint32_t current_seed=0;
    std::deque<int32_t> external_golden;
    bool use_external=false;
    Test() {
        if (const char* path = std::getenv("TRACE_FILE")) {
            Verilated::traceEverOn(true);
            dut.trace(&trace, 99);
            trace.open(path);
            tracing=true;
        }
        dut.clk=0; dut.rst_n=1; dut.in_valid=0; dut.out_ready=0;
        dut.group_first=0; dut.group_last=0; dut.row_id=0; dut.group_id=0;
    }
    ~Test() { dut.final(); if (tracing) trace.close(); }
    void eval() { dut.eval(); if (tracing) trace.dump(sim_time++); }
    [[noreturn]] void fail(const std::string& message) {
        throw std::runtime_error(message + " seed=" + std::to_string(current_seed)
                                 + " cycle=" + std::to_string(cycles));
    }
    void drive(const Beat& b) {
#if TEST_LANES == 16
        uint64_t packed=0;
        for(int i=0;i<TEST_LANES;i++) packed |= uint64_t(b.w[i]&15) << (4*i);
        dut.weight_data=packed;
#else
        for(int j=0;j<TEST_LANES/8;j++) {
            uint32_t packed=0;
            for(int i=0;i<8;i++) packed |= uint32_t(b.w[j*8+i]&15) << (4*i);
            dut.weight_data[j]=packed;
        }
#endif
        for(int j=0;j<TEST_LANES/4;j++) {
            uint32_t packed=0;
            for(int i=0;i<4;i++) packed |= uint32_t(b.x[j*4+i]&255) << (8*i);
            dut.activation_data[j]=packed;
        }
        dut.row_id=b.row; dut.group_id=b.group;
        dut.group_first=b.first; dut.group_last=b.last;
    }
    void reset() {
        dut.clk=0; dut.in_valid=0; dut.out_ready=0; dut.rst_n=0; eval();
        if(dut.out_valid || dut.in_ready) fail("reset interface");
        dut.clk=1; eval(); dut.clk=0; eval();
        dut.rst_n=1; eval();
        expected.clear(); ref_sum=0; active=false; beat_count=0;
    }
    bool step(const Beat* b, bool valid, bool ready) {
        dut.clk=0; dut.in_valid=valid; dut.out_ready=ready;
        if(b) drive(*b);
        eval();
        bool input_fire=dut.in_valid && dut.in_ready;
        bool held=dut.out_valid && !dut.out_ready;
        uint32_t held_sum=dut.partial_sum;
        unsigned held_row=dut.out_row_id, held_group=dut.out_group_id;
        if(dut.out_valid && dut.out_ready) {
            if(expected.empty()) fail("unexpected/duplicate output");
            auto e=expected.front(); expected.pop_front();
            if(int(dut.out_row_id)!=e.row || int(dut.out_group_id)!=e.group ||
               int32_t(dut.partial_sum)!=e.sum) fail("result/tag mismatch");
            ++received;
        }
        if(input_fire) {
            if(!b) fail("missing input payload");
            if(b->first) {
                if(active) fail("early group_first");
                active=true; ref_sum=0; beat_count=0;
                current_row=b->row; current_group=b->group;
            }
            if(!active || b->row!=current_row || b->group!=current_group)
                fail("input group protocol");
            for(int i=0;i<TEST_LANES;i++) ref_sum+=b->w[i]*b->x[i];
            ++beat_count;
            if(b->last != (beat_count==128/TEST_LANES)) fail("group length");
            if(b->last) {
                int32_t target=ref_sum;
                if(use_external) {
                    if(external_golden.empty()) fail("external golden exhausted");
                    target=external_golden.front(); external_golden.pop_front();
                    if(target!=ref_sum) fail("B golden disagrees with decoded inputs");
                }
                expected.push_back({b->row,b->group,target});
                active=false;
            }
            ++accepted;
        }
        if(!valid) ++input_idle;
        if(held) ++output_stall;
        dut.clk=1; eval();
        if(held && (!dut.out_valid || dut.partial_sum!=held_sum ||
                    dut.out_row_id!=held_row || dut.out_group_id!=held_group))
            fail("output changed under backpressure");
        dut.clk=0; eval(); ++cycles;
        return input_fire;
    }
    void run(const std::vector<Beat>& beats, uint32_t seed, bool stalls) {
        current_seed=seed;
        std::mt19937 rng(seed);
        size_t index=0; bool pending=false; uint64_t start=cycles;
        while(index<beats.size() || !expected.empty() || dut.out_valid) {
            if(cycles-start>beats.size()*100+1000) fail("timeout/deadlock");
            if(index<beats.size() && !pending) pending=!stalls || rng()%4!=0;
            bool ready=!stalls || rng()%3!=0;
            bool fire=step(index<beats.size()? &beats[index]:nullptr,pending,ready);
            if(fire) { ++index; pending=false; }
        }
        if(active) fail("unfinished input group");
    }
};
static std::vector<Beat> make_case(int n,int k,uint32_t seed,int mode) {
    std::mt19937 rng(seed);
    std::vector<int> x(k), w(n*k);
    for(auto& v:x) v=int(rng()%256)-128;
    for(auto& v:w) v=int(rng()%16)-8;
    if(mode==1) { for(auto& v:x)v=-128; for(auto& v:w)v=-8; }
    if(mode==2) { for(auto& v:x)v=-128; for(auto& v:w)v=7; }
    if(mode==3) { for(auto& v:w)v=0; }
    std::vector<Beat> beats;
    for(int row=0;row<n;row++) for(int g=0;g<(k+127)/128;g++)
        for(int b=0;b<128/TEST_LANES;b++) {
            Beat beat; beat.row=row; beat.group=g;
            beat.first=b==0; beat.last=b==128/TEST_LANES-1;
            for(int lane=0;lane<TEST_LANES;lane++) {
                int col=g*128+b*TEST_LANES+lane;
                if(col<k) { beat.w[lane]=w[row*k+col]; beat.x[lane]=x[col]; }
            }
            beats.push_back(beat);
        }
    return beats;
}
int main(int argc,char** argv) {
    Verilated::commandArgs(argc,argv);
    try {
        Test test; test.reset(); int cases=0;
        if(argc==3 && std::string(argv[1])=="--case") {
            VectorCase data(argv[2]); std::vector<Beat> beats;
            for(int row=0;row<data.n;row++) for(int col=0;col<data.padded;col+=TEST_LANES) {
                Beat b; b.row=row; b.group=col/128; b.first=col%128==0;
                b.last=col%128==128-TEST_LANES;
                for(int i=0;i<TEST_LANES;i++) { b.w[i]=data.w(row,col+i); b.x[i]=data.x(col+i); }
                beats.push_back(b);
            }
            test.use_external=true;
            for(bool stalls:{false,true}) {
                test.external_golden.assign(data.expected.begin(),data.expected.end());
                test.run(beats,20261017,stalls);
                if(!test.external_golden.empty()) test.fail("missing external results");
            }
            std::cout<<"PASS B_GOLDEN LANES="<<TEST_LANES<<" N="<<data.n<<" K="<<data.k
                     <<" modes=continuous,random_stall cycles="<<test.cycles<<'\n';
            return 0;
        }
        for(int k: {1,32,127,128,129,255,256,384,2048})
            for(int mode=0;mode<4;mode++) {
                auto beats=make_case(k==2048?8:3,k,1234+k+mode,mode);
                test.run(beats,1234+k+mode,true); ++cases;
            }
        for(uint32_t seed=0;seed<100;seed++) {
            test.run(make_case(1+seed%4,1+(seed*97)%600,seed,0),seed,true); ++cases;
        }
        // Explicit long output stall with the next group's input held valid.
        auto beats=make_case(2,128,77,0);
        for(int b=0;b<128/TEST_LANES;b++)
            if(!test.step(&beats[b],true,true)) test.fail("initial group stalled");
        for(int cycle=0;cycle<20;cycle++)
            if(test.step(&beats[128/TEST_LANES],true,false)) test.fail("accepted while blocked");
        std::vector<Beat> remaining(beats.begin()+128/TEST_LANES,beats.end());
        test.run(remaining,77,false); ++cases;
        // Reset midway through a group; no stale sum may survive.
        test.step(&beats[0],true,true); test.reset();
        test.run(make_case(1,128,88,0),88,false); ++cases;
        // Reset with a valid output waiting for its consumer.
        for(int b=0;b<128/TEST_LANES;b++) test.step(&beats[b],true,false);
        if(!test.dut.out_valid) test.fail("missing pre-reset pending output");
        test.reset(); test.run(make_case(1,129,99,0),99,true); ++cases;
        test.reset(); test.step(nullptr,false,true);
        auto bench_start=test.cycles;
        test.run(make_case(8,2048,20261011,0),20261011,false);
        std::cout << "BENCH LANES=" << TEST_LANES << " N=8 K=2048 seed=20261011"
                  << " input_stall=0 output_stall=0 cycles=" << test.cycles-bench_start
                  << " weight_bytes=8192 output_groups=128\n";
        std::cout << "PASS LANES=" << TEST_LANES << " cases=" << cases
                  << " cycles=" << test.cycles << " input_beats=" << test.accepted
                  << " output_groups=" << test.received << " input_idle=" << test.input_idle
                  << " output_stall=" << test.output_stall << '\n';
    } catch(const std::exception& e) {
        std::cerr << "FAIL LANES=" << TEST_LANES << " " << e.what() << '\n';
        return 1;
    }
    return 0;
}
