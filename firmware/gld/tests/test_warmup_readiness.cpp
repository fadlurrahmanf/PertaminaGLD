#include "GldWarmupReadiness.h"
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>

using Gate = pgl::gld::GldWarmupReadiness;

static Gate::Config config() {
    Gate::Config c{1000, 100, 200, 3, 2, {}};
    for (float& limit : c.maxSpreadVolts) limit = 0.1f;
    return c;
}
int main() {
    float values[8] = {};
    Gate gate(config());
    assert(gate.configValid() && !gate.ready(0));
    gate.reset(0);
    for (uint32_t t = 100; t <= 900; t += 100) gate.sample(t, values, 0xff);
    assert(gate.stableMask(900) == 0xff && !gate.ready(900));
    gate.sample(1000, values, 0xff);
    assert(gate.ready(1000));
    gate.sample(1001, values, 0xfe); // immediate invalidation, even too soon
    assert(!gate.ready(1001) && gate.stableMask(1001) == 0xfe);
    for (uint32_t t = 1100; t <= 1400; t += 100) gate.sample(t, values, 0xff);
    assert(gate.ready(1400));
    assert(!gate.ready(1601) && gate.stableMask(1601) == 0); // stale input
    gate.sample(1700, values, 0xff);
    assert(!gate.ready(1700) && gate.stableMask(1700) == 0);
    values[1] = std::numeric_limits<float>::quiet_NaN();
    for (uint32_t t = 1800; t <= 2400; t += 100) gate.sample(t, values, 0xff);
    assert(!gate.ready(2400) && gate.stableMask(2400) == 0xfd);
    values[1] = 0;
    for (uint32_t t = 2500; t <= 3000; t += 100) {
        values[2] += 0.2f;
        gate.sample(t, values, 0xff);
    }
    assert(!gate.ready(3000) && (gate.stableMask(3000) & 4) == 0);
    gate.reset(0xffffff00UL);
    for (uint32_t dt = 100; dt <= 1000; dt += 100)
        gate.sample(0xffffff00UL + dt, values, 0xff);
    assert(gate.ready(0xffffff00UL + 1000));
    auto bad = config(); bad.windowSamples = 0;
    Gate invalid(bad); invalid.reset(0); invalid.sample(1000, values, 0xff);
    assert(!invalid.configValid() && !invalid.ready(1000));
    bad = config(); bad.maxSpreadVolts[0] = NAN;
    assert(!Gate(bad).configValid());
}
