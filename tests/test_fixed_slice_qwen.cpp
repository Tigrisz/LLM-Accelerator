#include "Vtb_fixed_slice_qwen.h"
#include "verilated.h"
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <fstream>
#include <cstdlib>

class FixedSliceQwenBfm {
public:
    Vtb_fixed_slice_qwen dut;
    uint64_t cycles = 0;

    FixedSliceQwenBfm() {
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
        std::ofstream capture;
        if (const char* path = std::getenv("RESULT_CAPTURE")) {
            capture.open(path, std::ios::trunc);
            check(capture.is_open(), "cannot open result capture");
            capture << "{\"format_version\":1,\"source\":\"simulation\","
                       "\"run_id\":\"qwen-fixed-slice-rtl\",\"completed\":true,\"results\":[";
        }
        dut.rst_n = 0; tick(); tick(); dut.rst_n = 1; tick();
        dut.start = 1; tick(); dut.start = 0;
        unsigned captured = 0;
        for (int guard = 0; !dut.done && guard < 10000; ++guard) {
            tick();
            if (dut.result_count != captured) {
                check(dut.result_count == captured+1, "capture lost a result");
                if (capture.is_open()) {
                    if (captured) capture << ',';
                    capture << "{\"row_id\":" << captured << ",\"group_id\":0,\"partial_sum\":"
                            << int32_t(dut.last_partial_sum) << '}';
                }
                ++captured;
            }
        }
        check(dut.done, "Qwen fixed slice did not finish");
        check(dut.pass && !dut.fail, "Qwen fixed slice compare failed");
        check(dut.result_count == 16, "Qwen fixed slice result count");
        if (capture.is_open()) {
            capture << "]}\n";
            capture.flush();
            check(capture.good(), "result capture write failed");
        }
        std::cout << "PASS FIXED_SLICE_QWEN_RUN result_count=" << dut.result_count
                  << " cycles=" << cycles << " partial_sum="
                  << int32_t(dut.last_partial_sum) << '\n';
    }
};

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    try { FixedSliceQwenBfm test; test.run(); }
    catch (const std::exception& e) { std::cerr << "FAIL " << e.what() << '\n'; return 1; }
    return 0;
}
