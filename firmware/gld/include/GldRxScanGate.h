#pragma once
#include <cstdint>

namespace pgl { namespace gld {
// Pure scheduling decision; uint32_t subtraction remains safe across millis
// rollover. Hardware RX/ACK latency and SPI behavior require board validation.
inline bool shouldScanDuringRx(bool enabled, bool rxPending, bool inferenceMode,
                               bool batteryMode, bool adsAvailable,
                               uint32_t now, uint32_t rxStart, uint32_t lastScan,
                               uint32_t rxWindowMs, uint32_t scanIntervalMs) {
    return enabled && !rxPending && inferenceMode && !batteryMode && adsAvailable &&
           now - rxStart < rxWindowMs && now - lastScan >= scanIntervalMs;
}

// Read each channel only while no RX interrupt is pending. Callers publish
// readings only after a complete batch, so interrupted batches remain private.
template <typename Reading, typename Reader>
bool collectRxAwareScan(Reading* readings, uint8_t count,
                        const volatile bool* rxInterrupt, Reader read) {
    for (uint8_t channel = 0; channel < count; ++channel) {
        if (rxInterrupt && *rxInterrupt) return false;
        readings[channel] = read(channel);
    }
    return !(rxInterrupt && *rxInterrupt);
}
} }  // namespace pgl::gld
