#include "GldWorkflowRadioSchedule.h"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <cstddef>

// LoRa branch is extracted unmodified by the runner from the vendored SX126x
// getTimeOnAir(). The wide variant changes only the final multiply to 64-bit,
// so even vendor's uint32 intermediate overflow cannot disguise an underestimate.
#define RADIOLIB_SX126X_LORA_HEADER_EXPLICIT 0
struct Vendor {
    uint8_t spreadingFactor, codingRate, crcTypeLoRa, headerType;
    uint16_t preambleLengthLoRa;
    float bandwidthKhz;
    uint32_t actual(size_t len) {
#include "vendor_lora.inc"
    }
    uint64_t wide(size_t len) {
#include "vendor_lora_wide.inc"
    }
};

int main() {
    using pgl::gld::GldWorkflowRadioSchedule;
    unsigned comparisons = 0, wraps = 0;
    for (float bw : {7.8f,10.4f,15.6f,20.8f,31.25f,41.7f,62.5f,125.0f,250.0f,500.0f})
    for (uint8_t sf = 5; sf <= 12; ++sf)
    for (uint8_t cr = 5; cr <= 8; ++cr)
    for (uint16_t pre : {uint16_t(6),uint16_t(8),uint16_t(1024),uint16_t(65535)})
    for (uint16_t len : {uint16_t(1),uint16_t(39),uint16_t(255)})
    for (uint8_t crc : {uint8_t(0),uint8_t(1)})
    for (uint8_t hdr : {uint8_t(0),uint8_t(1)}) {
        Vendor radio{sf, static_cast<uint8_t>(cr - 4), crc, hdr, pre, bw};
        const uint64_t actual = radio.actual(len), wide = radio.wide(len);
        const uint32_t hz = static_cast<uint32_t>(static_cast<double>(bw) * 1000.0);
        uint32_t bound = 0;
        assert(GldWorkflowRadioSchedule::txTimeoutFromAppliedConfig(hz, sf, cr, pre, len,
                                                                    0x7fffffffu, 0, bound));
        assert(uint64_t(bound) >= 5u + (5u * actual + 999u) / 1000u);
        assert(uint64_t(bound) >= 5u + (5u * wide + 999u) / 1000u);
        if (wide != actual) ++wraps;
        ++comparisons;
    }
    assert(wraps > 0);
    std::printf("PASS %u vendor comparisons incl. %u uint32 overflow cases\n", comparisons, wraps);
}
