#include "GldWarmupSession.h"
#include <cassert>
#include <cstdint>

using Readiness = pgl::gld::GldWarmupReadiness;
using Session = pgl::gld::GldWarmupSession;

int main() {
    Readiness::Config c{1000, 100, 200, 3, 2, {}};
    for (float& limit : c.maxSpreadVolts) limit = .1f;
    float values[8]{};
    Session s(c);
    assert(s.configured() && s.state() == Session::State::Inactive && !s.blocksInference());
    s.updatePower(0, true, false);
    assert(s.state() == Session::State::Warming && s.blocksInference());
    assert(!s.observe(100, values, 0xff) && s.stableMask(100) == 0);
    s.updatePower(100, true, true);
    for (uint32_t t = 200; t < 1100; t += 100) assert(!s.observe(t, values, 0xff));
    assert(s.observe(1100, values, 0xff));
    assert(s.state() == Session::State::Priming && !s.blocksInference());
    assert(s.stableMask(5000) == 0xff);
    assert(!s.observe(1200, values, 0xff));
    s.noteFreshInference(false);
    assert(s.state() == Session::State::Priming);
    s.noteFreshInference(true);
    assert(s.state() == Session::State::Ready);
    values[0] = 100; // A gas-driven change must not silently restart warmup.
    assert(!s.observe(1300, values, 0xff) && s.state() == Session::State::Ready);
    s.updatePower(1400, true, false);
    assert(s.state() == Session::State::Warming && s.blocksInference());
    s.updatePower(1500, true, true);
    assert(s.elapsedMs(1500) == 0 && s.stableMask(1500) == 0);
    s.updatePower(1600, false, false);
    assert(s.state() == Session::State::Inactive && !s.blocksInference());
    c.windowSamples = 0;
    Session invalid(c); invalid.updatePower(0, true, true);
    for (uint32_t t = 100; t <= 3000; t += 100) assert(!invalid.observe(t, values, 0xff));
    assert(!invalid.configured() && invalid.blocksInference());
}
