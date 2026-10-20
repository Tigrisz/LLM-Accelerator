#include "Vtb_fixed_slice_qwen_multigroup.h"
#include "verilated.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

class FixedSliceQwenMultiGroupBfm {
public:
    Vtb_fixed_slice_qwen_multigroup dut;
    uint64_t cycles = 0;

    FixedSliceQwenMultiGroupBfm() {
        dut.clk = 0; dut.rst_n = 1; dut.start = 0;
    }
    void eval() { dut.eval(); }
    void tick() {
        dut.clk = 0; eval(); dut.clk = 1; eval(); dut.clk = 0; eval(); ++cycles;
    }
    void check(bool ok, const char* msg) {
        if (!ok) throw std::runtime_error(std::string(msg) + " cycle=" + std::to_string(cycles));
    }
    void run() {
        dut.rst_n = 0; tick(); tick(); dut.rst_n = 1; tick();
        dut.start = 1; tick(); dut.start = 0;
        for (int guard = 0; !dut.done && guard < 200000; ++guard) tick();
        check(dut.done, "Qwen multi-group slice did not finish");
        check(dut.pass && !dut.fail, "Qwen multi-group slice compare failed");
        check(dut.result_count == 256, "Qwen multi-group result count");
        std::cout << "PASS FIXED_SLICE_QWEN_MULTIGROUP_RUN result_count="
                  << dut.result_count << " cycles=" << cycles
                  << " partial_sum=" << int32_t(dut.last_partial_sum) << '\n';
    }
};

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    try { FixedSliceQwenMultiGroupBfm test; test.run(); }
    catch (const std::exception& e) { std::cerr << "FAIL " << e.what() << '\n'; return 1; }
    return 0;
}
