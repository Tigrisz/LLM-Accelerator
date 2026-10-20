#include "Vtb_lane_adapter.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <deque>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

struct InputBeat {
    std::array<uint32_t, 4> weight{};
    std::array<uint32_t, 8> activation{};
    bool first = false;
    bool last = false;
    uint16_t row = 0;
    uint16_t group = 0;
};

struct ExpectedBeat {
    uint64_t weight = 0;
    std::array<uint32_t, 4> activation{};
    bool first = false;
    bool last = false;
    uint16_t row = 0;
    uint16_t group = 0;
};

class AdapterBfm {
public:
    Vtb_lane_adapter dut;
    uint64_t cycles = 0;
    std::deque<ExpectedBeat> expected;
    bool held_output = false;
    uint64_t held_weight = 0;
    std::array<uint32_t, 4> held_activation{};
    bool held_first = false, held_last = false;
    uint16_t held_row = 0, held_group = 0;
    bool held_input = false;
    InputBeat held_input_value;

    AdapterBfm() {
        dut.clk = 0; dut.rst_n = 1;
        dut.in_valid = 0; dut.in_group_first = 0; dut.in_group_last = 0;
        dut.in_row_id = 0; dut.in_group_id = 0; dut.out_ready = 0;
        for (int i = 0; i < 4; ++i) dut.in_weight_data[i] = 0;
        for (int i = 0; i < 8; ++i) dut.in_activation_data[i] = 0;
    }

    void eval() { dut.eval(); }
    void check(bool ok, const char* message) {
        if (!ok) throw std::runtime_error(std::string(message) +
                                          " cycle=" + std::to_string(cycles));
    }
    void tick() {
        dut.clk = 0; eval();
        dut.clk = 1; eval();
        dut.clk = 0; eval();
        ++cycles;
    }
    void reset() {
        dut.rst_n = 0; dut.in_valid = 0; dut.out_ready = 0;
        tick(); tick();
        dut.rst_n = 1; tick();
        expected.clear(); held_output = false; held_input = false;
        check(!dut.out_valid && dut.in_ready, "reset handshake state");
    }
    void drive(const InputBeat& beat) {
        dut.in_valid = 1;
        for (int i = 0; i < 4; ++i) dut.in_weight_data[i] = beat.weight[i];
        for (int i = 0; i < 8; ++i) dut.in_activation_data[i] = beat.activation[i];
        dut.in_group_first = beat.first; dut.in_group_last = beat.last;
        dut.in_row_id = beat.row; dut.in_group_id = beat.group;
    }
    ExpectedBeat expected_half(const InputBeat& beat, bool high) {
        ExpectedBeat value;
        value.weight = uint64_t(beat.weight[high ? 2 : 0]) |
                       (uint64_t(beat.weight[high ? 3 : 1]) << 32);
        for (int i = 0; i < 4; ++i)
            value.activation[i] = beat.activation[(high ? 4 : 0) + i];
        value.first = !high && beat.first;
        value.last = high && beat.last;
        value.row = beat.row; value.group = beat.group;
        return value;
    }
    void check_output(const ExpectedBeat& value) {
        check(uint64_t(dut.out_weight_data) == value.weight, "weight half order");
        for (int i = 0; i < 4; ++i)
            check(dut.out_activation_data[i] == value.activation[i], "activation half order");
        check(bool(dut.out_group_first) == value.first, "group_first mapping");
        check(bool(dut.out_group_last) == value.last, "group_last mapping");
        check(dut.out_row_id == value.row && dut.out_group_id == value.group,
              "row/group mapping");
    }
    void step() {
        eval();
        if (held_output) {
            check(dut.out_valid, "output valid dropped under backpressure");
            check(uint64_t(dut.out_weight_data) == held_weight, "held weight changed");
            for (int i = 0; i < 4; ++i)
                check(dut.out_activation_data[i] == held_activation[i], "held activation changed");
            check(bool(dut.out_group_first) == held_first && bool(dut.out_group_last) == held_last,
                  "held metadata changed");
            check(dut.out_row_id == held_row && dut.out_group_id == held_group,
                  "held tags changed");
        }
        if (held_input) {
            check(dut.in_valid, "input valid dropped under backpressure");
            for (int i = 0; i < 4; ++i)
                check(dut.in_weight_data[i] == held_input_value.weight[i], "held input weight changed");
            for (int i = 0; i < 8; ++i)
                check(dut.in_activation_data[i] == held_input_value.activation[i], "held input activation changed");
        }

        bool input_fire = dut.in_valid && dut.in_ready;
        bool output_fire = dut.out_valid && dut.out_ready;
        if (input_fire) {
            InputBeat beat;
            for (int i = 0; i < 4; ++i) beat.weight[i] = dut.in_weight_data[i];
            for (int i = 0; i < 8; ++i) beat.activation[i] = dut.in_activation_data[i];
            beat.first = dut.in_group_first; beat.last = dut.in_group_last;
            beat.row = dut.in_row_id; beat.group = dut.in_group_id;
            expected.push_back(expected_half(beat, false));
            expected.push_back(expected_half(beat, true));
        }
        if (output_fire) {
            check(!expected.empty(), "unexpected output beat");
            check_output(expected.front());
            expected.pop_front();
        }

        held_output = dut.out_valid && !dut.out_ready;
        if (held_output) {
            held_weight = dut.out_weight_data;
            for (int i = 0; i < 4; ++i) held_activation[i] = dut.out_activation_data[i];
            held_first = dut.out_group_first; held_last = dut.out_group_last;
            held_row = dut.out_row_id; held_group = dut.out_group_id;
        }
        held_input = dut.in_valid && !dut.in_ready;
        if (held_input) {
            for (int i = 0; i < 4; ++i) held_input_value.weight[i] = dut.in_weight_data[i];
            for (int i = 0; i < 8; ++i) held_input_value.activation[i] = dut.in_activation_data[i];
            held_input_value.first = dut.in_group_first; held_input_value.last = dut.in_group_last;
            held_input_value.row = dut.in_row_id; held_input_value.group = dut.in_group_id;
        }
        tick();
    }
    std::vector<InputBeat> make_stream() {
        std::vector<InputBeat> values;
        for (int beat = 0; beat < 8; ++beat) {
            InputBeat value;
            for (int word = 0; word < 4; ++word)
                value.weight[word] = 0x10000000u + uint32_t(beat * 0x01010101u) + uint32_t(word * 0x00112233u);
            for (int word = 0; word < 8; ++word)
                value.activation[word] = 0x80000000u + uint32_t(beat * 0x01020304u) + uint32_t(word * 0x00010001u);
            value.first = (beat == 0 || beat == 4);
            value.last = (beat == 3 || beat == 7);
            value.row = uint16_t(beat < 4 ? 2 : 3);
            value.group = uint16_t(beat < 4 ? 5 : 6);
            values.push_back(value);
        }
        return values;
    }
    void run_stream() {
        reset();
        auto inputs = make_stream();
        size_t next = 0;
        bool driving = false;
        std::mt19937 rng(0x3216);
        while (next < inputs.size() || driving || !expected.empty() || dut.out_valid) {
            check(cycles < 1000, "adapter stream timeout");
            if (!driving && next < inputs.size()) {
                drive(inputs[next]);
                driving = true;
            }
            dut.out_ready = (rng() % 4) != 0;
            eval();
            bool fire = dut.in_valid && dut.in_ready;
            step();
            if (fire) {
                dut.in_valid = 0;
                driving = false;
                ++next;
            }
        }
        check(expected.empty() && !dut.out_valid, "adapter did not drain");
        std::cout << "PASS LANE_ADAPTER stream inputs=" << inputs.size()
                  << " outputs=" << inputs.size() * 2 << " cycles=" << cycles << '\n';
    }
    void reset_mid_beat() {
        reset();
        auto input = make_stream().front();
        drive(input); dut.out_ready = 1; eval();
        bool fire = dut.in_valid && dut.in_ready; check(fire, "reset setup input handshake");
        step(); dut.in_valid = 0;
        check(dut.out_valid, "first half missing before reset");
        dut.out_ready = 1; step();
        check(dut.out_valid, "second half missing before reset");
        dut.out_ready = 0; step();
        dut.rst_n = 0; tick();
        dut.rst_n = 1; tick();
        expected.clear();
        check(!dut.out_valid && dut.in_ready, "reset did not clear partial beat");
        std::cout << "PASS LANE_ADAPTER reset_mid_beat\n";
    }
};

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    try {
        AdapterBfm test;
        test.run_stream();
        test.reset_mid_beat();
    } catch (const std::exception& e) {
        std::cerr << "FAIL " << e.what() << '\n';
        return 1;
    }
    return 0;
}
