#include "Vtb_control.h"
#include "verilated.h"
#include "vector_case.h"
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
constexpr uint8_t CTRL = 0x00;
constexpr uint8_t STATUS = 0x04;
constexpr uint8_t WEIGHT_BASE_LO = 0x08;
constexpr uint8_t WEIGHT_BASE_HI = 0x0c;
constexpr uint8_t ACT_BASE_LO = 0x10;
constexpr uint8_t ACT_BASE_HI = 0x14;
constexpr uint8_t N_ROWS = 0x18;
constexpr uint8_t K_ELEMS = 0x1c;
constexpr uint8_t ERROR_CODE = 0x20;
constexpr uint8_t CYCLE_COUNT = 0x24;
constexpr uint8_t RESULT_COUNT = 0x28;
constexpr uint32_t CTRL_START = 1u;
constexpr uint32_t CTRL_CLEAR_STATUS = 2u;
constexpr uint32_t STATUS_BUSY = 1u << 0;
constexpr uint32_t STATUS_DONE = 1u << 1;
constexpr uint32_t STATUS_ERROR = 1u << 2;
constexpr uint32_t STATUS_ACT_LOADED = 1u << 3;
}

class ControlBfm {
public:
    Vtb_control dut;
    uint64_t cycles = 0;
    int outputs = 0;
    const VectorCase* data = nullptr;

    ControlBfm() {
        dut.clk = 0; dut.rst_n = 1;
        dut.bus_valid = 0; dut.bus_write = 0; dut.bus_addr = 0;
        dut.bus_wdata = 0; dut.bus_wstrb = 0xf;
        dut.host_wr_valid = 0; dut.host_wr_addr = 0; dut.host_wr_strb = 0xffff;
        dut.host_load_start = 0; dut.host_load_valid = 0;
        dut.host_load_last = 0; dut.host_load_valid_elems = 0;
        dut.result_ready = 0;
        for (int i = 0; i < 4; ++i) dut.host_wr_data[i] = 0;
        for (int i = 0; i < 8; ++i) dut.host_load_data[i] = 0;
    }

    void eval() { dut.eval(); }
    void check(bool ok, const char* msg) {
        if (!ok) throw std::runtime_error(std::string(msg) + " cycle=" + std::to_string(cycles));
    }
    void tick() {
        dut.clk = 0; eval();
        dut.clk = 1; eval();
        dut.clk = 0; eval();
        ++cycles;
    }
    void reset() {
        dut.rst_n = 0; dut.bus_valid = 0; dut.host_wr_valid = 0;
        dut.host_load_start = 0; dut.host_load_valid = 0; dut.result_ready = 0;
        tick(); tick();
        dut.rst_n = 1; tick();
        check(!dut.busy && !dut.done && !dut.error, "reset status");
    }
    void bus_write(uint8_t addr, uint32_t value) {
        dut.bus_valid = 1; dut.bus_write = 1; dut.bus_addr = addr;
        dut.bus_wdata = value; dut.bus_wstrb = 0xf;
        eval(); check(dut.bus_ready, "bus not ready for write"); tick();
        dut.bus_valid = 0; dut.bus_write = 0;
    }
    uint32_t bus_read(uint8_t addr) {
        dut.bus_valid = 1; dut.bus_write = 0; dut.bus_addr = addr;
        eval(); check(dut.bus_ready, "bus not ready for read");
        uint32_t value = dut.bus_rdata;
        tick(); dut.bus_valid = 0;
        return value;
    }
    void preload(const VectorCase& c) {
        data = &c;
        for (size_t pos = 0; pos < c.weights.size(); pos += 16) {
            dut.host_wr_valid = 1; dut.host_wr_addr = 256 + pos;
            for (int word = 0; word < 4; ++word) {
                uint32_t value = 0;
                for (int j = 0; j < 4; ++j)
                    value |= uint32_t(c.weights[pos + word * 4 + j]) << (8 * j);
                dut.host_wr_data[word] = value;
            }
            eval(); check(dut.host_wr_ready, "memory preload not ready"); tick();
        }
        dut.host_wr_valid = 0;
        dut.host_load_start = 1; tick(); dut.host_load_start = 0;
        for (int pos = 0; pos < c.padded; pos += 32) {
            dut.host_load_valid = 1; dut.host_load_last = (pos + 32 == c.padded);
            dut.host_load_valid_elems = uint16_t(std::max(0, std::min(32, c.k - pos)));
            for (int word = 0; word < 8; ++word) {
                uint32_t value = 0;
                for (int j = 0; j < 4; ++j)
                    value |= uint32_t(c.activations[pos + word * 4 + j]) << (8 * j);
                dut.host_load_data[word] = value;
            }
            eval(); check(dut.host_load_ready, "activation preload not ready"); tick();
        }
        dut.host_load_valid = 0; dut.host_load_last = 0;
        eval(); check(dut.host_loaded && dut.host_loaded_k == unsigned(c.k), "activation not loaded");
    }
    void configure(const VectorCase& c) {
        bus_write(WEIGHT_BASE_LO, 256); bus_write(WEIGHT_BASE_HI, 0);
        bus_write(ACT_BASE_LO, 0x1000); bus_write(ACT_BASE_HI, 0);
        bus_write(N_ROWS, c.n); bus_write(K_ELEMS, c.k);
    }
    void run_case(const VectorCase& c) {
        reset(); preload(c); configure(c);
        check((bus_read(STATUS) & STATUS_ACT_LOADED) != 0, "status lost activation loaded");
        bus_write(CTRL, CTRL_START);
        int guard = 0;
        while (!dut.done) {
            check(guard++ < 100000, "control run timeout");
            dut.result_ready = (guard % 4) != 0;
            if (dut.result_valid && dut.result_ready) {
                check(outputs < int(c.expected.size()), "too many results");
                check(int32_t(dut.partial_sum) == c.expected[outputs], "result mismatch");
                check(dut.result_row_id == unsigned(outputs / (c.padded / 128)), "result row tag");
                check(dut.result_group_id == unsigned(outputs % (c.padded / 128)), "result group tag");
                ++outputs;
            }
            tick();
        }
        check(outputs == int(c.expected.size()), "done before all outputs accepted");
        uint32_t status = bus_read(STATUS);
        check((status & STATUS_DONE) != 0 && (status & STATUS_BUSY) == 0, "terminal status");
        check((status & STATUS_ERROR) == 0, "unexpected error status");
        check(bus_read(RESULT_COUNT) == unsigned(outputs), "result count register");
        std::cout << "PASS CONTROL N=" << c.n << " K=" << c.k
                  << " outputs=" << outputs << " cycles=" << cycles << '\n';
    }
    void error_cases() {
        reset();
        bus_write(N_ROWS, 0); bus_write(K_ELEMS, 128); bus_write(CTRL, CTRL_START);
        for (int i = 0; i < 3; ++i) tick();
        check(!dut.busy && dut.error, "zero-N error missing");
        check(bus_read(ERROR_CODE) == 1, "zero-N error code");
        bus_write(CTRL, CTRL_CLEAR_STATUS);
        // CTRL commands are registered in control_regs and consumed by the
        // controller on the following clock edge. Give that pulse one cycle
        // to reach the FSM before sampling STATUS.
        tick();
        check((bus_read(STATUS) & STATUS_ERROR) == 0, "clear status failed");
        bus_write(N_ROWS, 1); bus_write(K_ELEMS, 128); bus_write(CTRL, CTRL_START);
        for (int i = 0; i < 2; ++i) tick();
        check(dut.error && bus_read(ERROR_CODE) == 4, "activation-not-loaded error missing");
        std::cout << "PASS CONTROL_ERRORS\n";
    }
};

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    try {
        ControlBfm test;
        if (argc == 2 && std::string(argv[1]) == "--errors") {
            test.error_cases();
        } else if (argc == 2) {
            VectorCase c(argv[1]);
            test.outputs = 0;
            test.run_case(c);
        } else {
            throw std::runtime_error("usage: control case.txt | --errors");
        }
    } catch (const std::exception& e) {
        std::cerr << "FAIL " << e.what() << '\n';
        return 1;
    }
    return 0;
}
