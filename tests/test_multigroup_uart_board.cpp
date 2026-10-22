#include "Vtb_multigroup_uart_board.h"
#include "verilated.h"
#include "uart_test_decoder.h"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#ifndef TEST_K
#define TEST_K 256
#endif
#ifndef TEST_CAPTURE_DEPTH
#define TEST_CAPTURE_DEPTH 6
#endif
static constexpr unsigned DIV = 234;
static constexpr unsigned GROUPS = (TEST_K + 127) / 128;
static constexpr unsigned TOTAL = 3 * GROUPS;
static constexpr unsigned COUNT = std::min(unsigned(TEST_CAPTURE_DEPTH), TOTAL);

static void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
static void tick(Vtb_multigroup_uart_board &d) {
    d.clk = 0; d.eval(); d.clk = 1; d.eval();
}
static void reset(Vtb_multigroup_uart_board &d) {
    d.rst_n = 0;
    for (unsigned i = 0; i < 5; ++i) tick(d);
    require(d.uart_tx && !d.led_done && !d.led_pass && !d.led_fail,
            "reset did not clear UART/status");
    d.rst_n = 1;
}
static uint32_t le32(const std::vector<uint8_t> &b, size_t p) {
    return uint32_t(b[p]) | (uint32_t(b[p+1]) << 8) |
           (uint32_t(b[p+2]) << 16) | (uint32_t(b[p+3]) << 24);
}
static std::vector<uint8_t> receive(Vtb_multigroup_uart_board &d) {
    UartTestDecoder rx(DIV);
    const unsigned size = 9 + 8 * COUNT;
    bool saw_busy = false;
    for (unsigned c = 0; c < size * 12 * DIV + 50000; ++c) {
        tick(d); rx.sample(d.uart_tx);
        saw_busy = saw_busy || d.led_busy;
        if (!rx.bytes.empty()) require(d.led_done, "UART before computation done");
        if (rx.bytes.size() == size) {
            require(saw_busy && d.led_done && !d.led_busy, "compute status mismatch");
            require(bool(d.led_pass) == (COUNT == TOTAL) &&
                    bool(d.led_fail) == (COUNT != TOTAL), "capture count/overflow LED mismatch");
            for (unsigned i = 0; i < 30 * DIV; ++i) { tick(d); rx.sample(d.uart_tx); }
            require(rx.bytes.size() == size && d.uart_tx, "unexpected repeated frame");
            return rx.bytes;
        }
    }
    throw std::runtime_error("UART frame timeout");
}
static void verify(const std::vector<uint8_t> &b, const std::vector<uint32_t> &golden) {
    require(b[0] == 0xa5 && b[1] == 0x5a && b[2] == 1, "header mismatch");
    require(le32(b, 3) == COUNT, "record count mismatch");
    for (unsigned i = 0; i < COUNT; ++i) {
        unsigned p = 7 + 8 * i;
        unsigned row = unsigned(b[p]) | (unsigned(b[p+1]) << 8);
        unsigned group = unsigned(b[p+2]) | (unsigned(b[p+3]) << 8);
        require(row == i / GROUPS && group == i % GROUPS, "row/group order mismatch");
        require(le32(b, p+4) == golden[i], "partial_sum mismatch");
    }
    require(b[b.size()-2] == 0x5a && b.back() == 0xa5, "footer mismatch");
}
int main(int argc, char **argv) {
    try {
        require(argc == 3, "expected golden.mem and simulation output prefix");
        Verilated::commandArgs(argc, argv);
        std::ifstream input(argv[1]);
        require(bool(input), "cannot open expected.mem");
        std::vector<uint32_t> golden;
        std::string word;
        while (input >> word) golden.push_back(uint32_t(std::stoul(word, nullptr, 16)));
        require(golden.size() == TOTAL, "expected image dimensions mismatch");
        Vtb_multigroup_uart_board d;
        reset(d);
        UartTestDecoder interrupted(DIV);
        for (unsigned c = 0; c < 200000 && interrupted.bytes.size() < 12; ++c) {
            tick(d); interrupted.sample(d.uart_tx);
        }
        require(interrupted.bytes.size() == 12, "mid-frame reset not exercised");
        std::vector<uint8_t> first;
        for (unsigned run = 1; run <= 3; ++run) {
            reset(d);
            const auto bytes = receive(d);
            verify(bytes, golden);
            if (run == 1) first = bytes;
            else require(bytes == first, "reset rerun differs");
            std::ofstream output(std::string(argv[2]) + "_run" + std::to_string(run) + ".bin",
                                 std::ios::binary);
            output.write(reinterpret_cast<const char *>(bytes.data()), bytes.size());
            require(bool(output), "cannot save simulation capture");
        }
        std::cout << "PASS A_MULTIGROUP_UART source=simulation N=3 K=" << TEST_K
                  << " records=" << COUNT << " bytes=" << first.size()
                  << " resets=3 mid_tx_reset=1 overflow=" << (COUNT != TOTAL) << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL A_MULTIGROUP_UART " << error.what() << '\n';
        return 1;
    }
}
