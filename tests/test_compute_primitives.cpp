#include "Vtb_compute_primitives.h"
#include "verilated.h"
#include <cstdint>
#include <iostream>

#ifndef TEST_LANES
#define TEST_LANES 32
#endif

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vtb_compute_primitives dut;
    int products = 0;
    for (int w = -8; w <= 7; ++w) {
        for (int x = -128; x <= 127; ++x) {
            dut.weight = w & 15;
            dut.activation = x & 255;
            dut.eval();
            int got = dut.product & 4095;
            if (got & 2048) got -= 4096;
            if (got != w * x) {
                std::cerr << "FAIL product w=" << w << " x=" << x
                          << " got=" << got << " expected=" << w*x << '\n';
                return 1;
            }
            ++products;
        }
    }
    // Shift the 16 nibble values across all lanes, checking packing and extension.
    for (int offset = 0; offset < 16; ++offset) {
#if TEST_LANES == 16
        uint64_t packed64 = 0;
        for (int lane = 0; lane < TEST_LANES; ++lane)
            packed64 |= uint64_t((lane+offset) & 15) << (4*lane);
        dut.packed_weights = packed64;
#else
        for (int word = 0; word < TEST_LANES/8; ++word) {
            uint32_t packed = 0;
            for (int j = 0; j < 8; ++j)
                packed |= uint32_t((word*8+j+offset) & 15) << (4*j);
            dut.packed_weights[word] = packed;
        }
#endif
        dut.eval();
        for (int lane = 0; lane < TEST_LANES; ++lane) {
            int nibble = (lane+offset) & 15;
            int expected = nibble < 8 ? nibble : nibble-16;
            int got = (dut.signed_weights[lane/4] >> (8*(lane%4))) & 255;
            if (got >= 128) got -= 256;
            if (got != expected) {
                std::cerr << "FAIL unpack lane=" << lane << " offset=" << offset << '\n';
                return 1;
            }
        }
    }
    dut.final();
    std::cout << "PASS LANES=" << TEST_LANES << " products=" << products
              << " unpack_checks=" << TEST_LANES*16 << '\n';
    return 0;
}
