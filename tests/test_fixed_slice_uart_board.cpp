#include "Vtb_fixed_slice_uart_board.h"
#include "uart_test_decoder.h"
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#include <stdexcept>

#ifndef TEST_CAPTURE_DEPTH
#define TEST_CAPTURE_DEPTH 256
#endif
static constexpr unsigned DIV = 234;
static constexpr unsigned TOTAL = 256;
static constexpr unsigned COUNT = TEST_CAPTURE_DEPTH < TOTAL ? TEST_CAPTURE_DEPTH : TOTAL;

static void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
static void tick(Vtb_fixed_slice_uart_board &d) {
    d.clk = 0; d.eval(); d.clk = 1; d.eval();
}
static void reset(Vtb_fixed_slice_uart_board &d) {
    d.rst_n = 0;
    for (int i = 0; i < 5; ++i) tick(d);
    require(d.uart_tx && !d.led_done && !d.led_pass && !d.led_fail,
            "reset did not clear status/UART");
    d.rst_n = 1;
}
static uint32_t le32(const std::vector<uint8_t> &b, size_t offset) {
    return uint32_t(b[offset]) | (uint32_t(b[offset+1]) << 8) |
           (uint32_t(b[offset+2]) << 16) | (uint32_t(b[offset+3]) << 24);
}
static std::vector<uint32_t> load_golden() {
    std::ifstream f("fpgatest/qwen_slice/prj/mem/expected.mem");
    require(bool(f), "missing PDS expected.mem");
    std::vector<uint32_t> result;
    std::string word;
    while (f >> word) result.push_back(uint32_t(std::stoul(word, nullptr, 16)));
    require(result.size() == TOTAL, "PDS expected image must contain 256 results");
    return result;
}
static std::vector<uint8_t> receive(Vtb_fixed_slice_uart_board &d) {
    UartTestDecoder rx(DIV);
    const unsigned frame_size = 9 + 8 * COUNT;
    bool saw_busy = false;
    for (unsigned c = 0; c < frame_size * 12 * DIV + 50000; ++c) {
        tick(d);
        saw_busy = saw_busy || d.led_busy;
        rx.sample(d.uart_tx);
        if (!rx.bytes.empty()) require(d.led_done, "UART emitted before computation completed");
        if (rx.bytes.size() == frame_size) {
            require(saw_busy && d.led_done && !d.led_busy, "compute status mismatch");
            const bool overflow = TEST_CAPTURE_DEPTH < TOTAL;
            require(bool(d.led_pass) == !overflow && bool(d.led_fail) == overflow,
                    "board PASS/FAIL must include capture overflow/count");
            for (unsigned n = 0; n < 30 * DIV; ++n) {
                tick(d); rx.sample(d.uart_tx);
            }
            require(rx.bytes.size() == frame_size && d.uart_tx, "unexpected repeat frame");
            return rx.bytes;
        }
    }
    throw std::runtime_error("UART full frame timeout");
}
static void verify(const std::vector<uint8_t> &b, const std::vector<uint32_t> &golden) {
    require(b[0] == 0xa5 && b[1] == 0x5a && b[2] == 1, "header mismatch");
    require(le32(b, 3) == COUNT, "wire count mismatch");
    for (unsigned i = 0; i < COUNT; ++i) {
        const unsigned pos = 7 + 8 * i;
        const unsigned row = unsigned(b[pos]) | (unsigned(b[pos+1]) << 8);
        const unsigned group = unsigned(b[pos+2]) | (unsigned(b[pos+3]) << 8);
        require(row == i / 16 && group == i % 16, "missing/duplicate/wrong row/group");
        if (le32(b, pos + 4) != golden[i]) {
            std::cerr << "mismatch row=" << row << " group=" << group << '\n';
            throw std::runtime_error("partial_sum differs from golden");
        }
    }
    require(b[b.size()-2] == 0x5a && b.back() == 0xa5, "footer mismatch");
}
int main() {
    try {
        Vtb_fixed_slice_uart_board d;
        const auto golden = load_golden();
        // Interrupt one transmission and ensure the next reset starts a new
        // complete frame from row=0,group=0 with no stale RAM entries.
        reset(d);
        UartTestDecoder interrupted(DIV);
        for (unsigned c = 0; c < 200000 && interrupted.bytes.size() < 12; ++c) {
            tick(d); interrupted.sample(d.uart_tx);
        }
        require(interrupted.bytes.size() == 12, "mid-frame reset was not exercised");
        std::vector<uint8_t> first;
        for (unsigned run = 0; run < 3; ++run) {
            reset(d);
            const auto bytes = receive(d);
            verify(bytes, golden);
            if (run == 0) first = bytes;
            else require(bytes == first, "reset rerun differs");
        }
        if (COUNT == TOTAL) {
            std::ofstream f("build/reports/qwen_uart_sim.bin", std::ios::binary);
            f.write(reinterpret_cast<const char *>(first.data()), first.size());
            require(bool(f), "cannot save simulation capture");
        }
        std::cout << "PASS QWEN_UART_BOARD records=" << COUNT << " bytes=" << first.size()
                  << " divisor=" << DIV << " resets=3 mid_tx_reset=1 overflow="
                  << (COUNT != TOTAL) << '\n';
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "FAIL QWEN_UART_BOARD " << e.what() << '\n';
        return 1;
    }
}
