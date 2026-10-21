#ifndef UART_TEST_DECODER_H
#define UART_TEST_DECODER_H
#include <cstdint>
#include <stdexcept>
#include <vector>

// Independent 8N1 receiver: sample the center of each bit, never inspect
// transmitter state. For divisor=1, sample one clock after start detection.
class UartTestDecoder {
    unsigned divisor_, wait_ = 0, bit_ = 0;
    bool active_ = false;
    uint8_t value_ = 0;
public:
    std::vector<uint8_t> bytes;
    explicit UartTestDecoder(unsigned divisor) : divisor_(divisor) {}
    void sample(bool tx) {
        if (!active_) {
            if (!tx) {
                active_ = true;
                wait_ = divisor_ + divisor_ / 2;
                bit_ = 0;
                value_ = 0;
            }
            return;
        }
        if (--wait_ != 0) return;
        if (bit_ < 8) {
            if (tx) value_ |= uint8_t(1u << bit_);
            ++bit_;
            wait_ = divisor_;
        } else {
            if (!tx) throw std::runtime_error("UART stop bit is low");
            bytes.push_back(value_);
            active_ = false;
        }
    }
};
#endif
