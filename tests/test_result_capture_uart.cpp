#include "Vtb_result_capture_uart.h"

#include <cstdint>
#include <iostream>
#include <vector>

struct Record {
    uint16_t row;
    uint16_t group;
    int32_t sum;
};

static void tick(Vtb_result_capture_uart *dut) {
    dut->clk = 0;
    dut->eval();
    dut->clk = 1;
    dut->eval();
}

static void reset(Vtb_result_capture_uart *dut) {
    dut->rst_n = 0;
    dut->capture_clear = 0;
    dut->capture_valid = 0;
    dut->tx_start = 0;
    dut->peek_index = 0;
    for (int i = 0; i < 3; ++i) tick(dut);
    dut->rst_n = 1;
    tick(dut);
}

static void clear_capture(Vtb_result_capture_uart *dut) {
    dut->capture_clear = 1;
    tick(dut);
    dut->capture_clear = 0;
    tick(dut);
}

static void push(Vtb_result_capture_uart *dut, const Record &r) {
    dut->capture_row_id = r.row;
    dut->capture_group_id = r.group;
    dut->capture_partial_sum = static_cast<uint32_t>(r.sum);
    dut->capture_valid = 1;
    tick(dut);
    dut->capture_valid = 0;
    tick(dut);
}

static bool check_capture(Vtb_result_capture_uart *dut,
                          const std::vector<Record> &records) {
    if (dut->capture_count != records.size() || dut->overflow != 0) {
        std::cerr << "capture count/overflow mismatch\n";
        return false;
    }
    for (unsigned i = 0; i < records.size(); ++i) {
        dut->peek_index = i;
        dut->eval();
        uint64_t packed = dut->peek_data;
        uint64_t expected = static_cast<uint64_t>(static_cast<uint32_t>(records[i].sum)) << 32;
        expected |= static_cast<uint64_t>(records[i].group) << 16;
        expected |= records[i].row;
        if (!dut->peek_valid || packed != expected) {
            std::cerr << "capture record mismatch at " << i << "\n";
            return false;
        }
    }
    return true;
}

static bool decode_uart(Vtb_result_capture_uart *dut,
                        const std::vector<Record> &records) {
    std::vector<uint8_t> bytes;
    bool in_frame = false;
    int bit = -1;
    uint8_t current = 0;
    for (int cycles = 0; cycles < 10000 && !dut->uart_done; ++cycles) {
        tick(dut);
        const bool level = dut->uart_tx != 0;
        if (!in_frame) {
            if (!level) {
                in_frame = true;
                bit = 0;
                current = 0;
            }
            continue;
        }
        if (bit < 8) {
            if (level) current |= static_cast<uint8_t>(1u << bit);
            ++bit;
        } else {
            if (!level) {
                std::cerr << "UART stop bit is low\n";
                return false;
            }
            bytes.push_back(current);
            in_frame = false;
            bit = -1;
        }
    }
    if (!dut->uart_done || bytes.size() != 7 + records.size() * 8 + 2) {
        std::cerr << "UART frame length/done mismatch: " << bytes.size() << "\n";
        return false;
    }
    if (bytes[0] != 0xa5 || bytes[1] != 0x5a || bytes[2] != 0x01 ||
        bytes[3] != records.size() || bytes[4] != 0 || bytes[5] != 0 || bytes[6] != 0) {
        std::cerr << "UART header mismatch\n";
        return false;
    }
    for (unsigned i = 0; i < records.size(); ++i) {
        const unsigned p = 7 + i * 8;
        const uint32_t sum = static_cast<uint32_t>(records[i].sum);
        const uint8_t expected[8] = {
            static_cast<uint8_t>(records[i].row), static_cast<uint8_t>(records[i].row >> 8),
            static_cast<uint8_t>(records[i].group), static_cast<uint8_t>(records[i].group >> 8),
            static_cast<uint8_t>(sum), static_cast<uint8_t>(sum >> 8),
            static_cast<uint8_t>(sum >> 16), static_cast<uint8_t>(sum >> 24)};
        for (unsigned b = 0; b < 8; ++b) {
            if (bytes[p + b] != expected[b]) {
                std::cerr << "UART record mismatch at " << i << ", byte " << b << "\n";
                return false;
            }
        }
    }
    const unsigned footer = 7 + records.size() * 8;
    return bytes[footer] == 0x5a && bytes[footer + 1] == 0xa5;
}

int main() {
    Vtb_result_capture_uart dut;
    dut.rst_n = 0;
    dut.clk = 0;
    dut.eval();
    reset(&dut);

    const std::vector<Record> records = {
        {0, 0, -255}, {0, 1, 17}, {1, 0, 123456},
        {1, 1, -7}, {2, 0, 0x12345678}, {2, 1, -1}};
    clear_capture(&dut);
    for (const Record &r : records) push(&dut, r);
    if (!check_capture(&dut, records)) return 1;

    dut.tx_start = 1;
    tick(&dut);
    dut.tx_start = 0;
    if (!dut.uart_busy || !decode_uart(&dut, records)) return 1;

    clear_capture(&dut);
    for (const Record &r : records) push(&dut, r);
    push(&dut, {9, 9, 9});
    if (dut.capture_count != records.size() || dut.overflow == 0) {
        std::cerr << "overflow behavior mismatch\n";
        return 1;
    }
    std::cout << "PASS RESULT_CAPTURE_UART records=" << records.size() << "\n";
    return 0;
}
