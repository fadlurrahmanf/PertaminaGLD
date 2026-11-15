#include "GldRxScanGate.h"
#include <cassert>
#include <cstdint>
using pgl::gld::shouldScanDuringRx;
int main() {
    // Normal 2 s RX with 500 ms sampling. Pending packet wins over scan.
    uint32_t last = 0; int scans = 0;
    for (uint32_t now = 0; now < 2000; now += 5) {
        const bool irq = now >= 1100;
        if (irq) { assert(!shouldScanDuringRx(true, irq, true, false, true, now, 0, last, 2000, 500)); break; }
        if (shouldScanDuringRx(true, irq, true, false, true, now, 0, last, 2000, 500)) { last = now; ++scans; }
    }
    assert(scans == 2);
    assert(!shouldScanDuringRx(false, false, true, false, true, 500, 0, 0, 2000, 500));
    assert(!shouldScanDuringRx(true, false, false, false, true, 500, 0, 0, 2000, 500));
    assert(!shouldScanDuringRx(true, false, true, true, true, 500, 0, 0, 2000, 500));
    assert(!shouldScanDuringRx(true, false, true, false, false, 500, 0, 0, 2000, 500));
    assert(!shouldScanDuringRx(true, false, true, false, true, 2000, 0, 0, 2000, 500));
    const uint32_t start = UINT32_MAX - 249;
    assert(shouldScanDuringRx(true, false, true, false, true, 250, start, start, 2000, 500));

    // An IRQ during a channel read aborts the batch before any later channel
    // is read. The caller must not publish this incomplete local array.
    volatile bool rx = false; int reads = 0; int samples[8] = {};
    const auto interruptedBatchComplete = pgl::gld::collectRxAwareScan(samples, 8, &rx, [&](uint8_t channel) {
        ++reads; if (channel == 2) rx = true; return static_cast<int>(channel + 1);
    });
    assert(!interruptedBatchComplete && reads == 3 && samples[3] == 0);
    rx = false; reads = 0;
    const auto complete = pgl::gld::collectRxAwareScan(samples, 8, &rx, [&](uint8_t channel) {
        ++reads; return static_cast<int>(channel + 1);
    });
    assert(complete && reads == 8 && samples[7] == 8);
}
