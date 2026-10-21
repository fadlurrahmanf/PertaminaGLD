// Exercises the real nulling service with deterministic ADC/DAC/NVS doubles.
// This verifies algorithm control flow only; it is not an analog or hardware test.
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "../../src/GldNullingService.cpp"

TwoWire Wire;
static uint32_t nowMs = 0;
static uint16_t codeByChannel[8]{};
static unsigned readsSinceWrite = 0;
static unsigned baselineSteps = 0;
static unsigned confirmSteps = 0;
static unsigned badSampleChannel = 99;
static bool maxOnlyCrossing = false;
static bool saturateAt2048 = false;
static bool negativeBaseline = false;
static std::vector<unsigned char> stored;
static std::vector<std::string> logs;

uint32_t millis() { return nowMs; }
void delay(uint32_t ms) { nowMs += ms; }

bool Preferences::begin(const char*, bool) { return true; }
void Preferences::end() {}
size_t Preferences::putBytes(const char*, const void* data, size_t n) {
    const auto* p = static_cast<const unsigned char*>(data);
    stored.assign(p, p + n);
    return n;
}
size_t Preferences::getBytes(const char*, void* data, size_t n) {
    if (stored.size() != n) return 0;
    std::memcpy(data, stored.data(), n);
    return n;
}

namespace pgl::gld {
bool GldAds1256Reader::begin(SPIClass&) { initialized_ = true; return true; }

static float voltageFor(uint16_t code) {
    if (maxOnlyCrossing) return code == board::GLD_DAC_CODE_MAX ? 0.020f : 0.010f;
    if (negativeBaseline) {
        if (code < 100) return -0.020f;
        if (code == 100) return 0.0080f;
        if (code == 101) return 0.0120f;
        if (code == 102) return 0.0102f;
        if (code == 103) return 0.0105f;
        return 0.0200f;
    }
    if (code < 100) return 0.010f;
    if (code == 100) return 0.020f;
    if (code == 101) return 0.018f;
    if (code == 102) return 0.016f;
    if (code == 103) return 0.0151f;
    return 0.020f;
}

GldAds1256Reading GldAds1256Reader::readChannel(uint8_t ch) {
    ++readsSinceWrite;
    nowMs += 1;
    const bool invalid = ch == badSampleChannel;
    const bool saturated = saturateAt2048 && codeByChannel[ch] == 2048u;
    return {invalid ? GldAds1256Status::NotReady : GldAds1256Status::Ok,
            0, voltageFor(codeByChannel[ch]), 64, saturated};
}

bool GldDacMux::begin(TwoWire&, GldPcf8574*) { initialized_ = true; return true; }
bool GldDacMux::writeDac(uint8_t ch, uint16_t code) {
    lastValue_[ch] = codeByChannel[ch] = code;
    readsSinceWrite = 0;
    return true;
}
uint16_t GldDacMux::lastValue(uint8_t ch) const { return lastValue_[ch]; }
}

static void logLine(const char* text) {
    logs.emplace_back(text);
    const std::string line(text);
#ifndef NATIVE_SCOPE_ONLY
    if (line.find("NULLING_BASELINE_STEP") == 0 && line.find("valid=1") != std::string::npos) {
        ++baselineSteps;
        assert(readsSinceWrite == 8u);
    }
    if (line.find("NULLING_CONFIRM_STEP") == 0 && line.find("valid=1") != std::string::npos) {
        ++confirmSteps;
        assert(readsSinceWrite == 10u);
    }
#endif
}

static bool hasLog(const char* text) {
    for (const auto& line : logs) if (line.find(text) != std::string::npos) return true;
    return false;
}

static unsigned countLog(const char* text) {
    unsigned count = 0;
    for (const auto& line : logs) if (line.find(text) != std::string::npos) ++count;
    return count;
}

static void resetFake() {
    nowMs = 0;
    readsSinceWrite = 0;
    baselineSteps = 0;
    confirmSteps = 0;
    badSampleChannel = 99;
    maxOnlyCrossing = false;
    saturateAt2048 = false;
    negativeBaseline = false;
    logs.clear();
    std::memset(codeByChannel, 0, sizeof(codeByChannel));
}

int main() {
    using namespace pgl::gld;
    GldAds1256Reader ads;
    GldDacMux dac;
    SPIClass spi;
    assert(ads.begin(spi));
    assert(dac.begin(Wire));

#ifdef NATIVE_SCOPE_ONLY
    static_assert(!GLD1_LEGACY_DETERMINISTIC_NULLING,
                  "protected profile must not select GLD1 legacy path");
    resetFake();
    uint16_t candidate = 100;
    DecisionIssue issue = DecisionIssue::None;
    GldNullingConfig config{};
    assert(confirmCode(ads, dac, 0, 0.010f, candidate, 164, logLine,
                       nullptr, config, 0.000001f, issue));
    assert(countLog("NULLING_CONFIRM_STEP") == 75u);
    assert(!hasLog("algorithm=gld1_legacy_deterministic"));
    std::puts("PASS: protected profile retains shared 75-point confirm path");
    return 0;
#else
    static_assert(GLD1_LEGACY_DETERMINISTIC_NULLING,
                  "this test targets gld_model_1 only");

    GldNullingConfig config{};
    config.thresholdV = 0.001f;
    assert(std::fabs(gld1LegacyThreshold(0.010f, config) - 0.005f) < 0.000001f);
    config.thresholdV = 0.020f;
    assert(std::fabs(gld1LegacyThreshold(0.010f, config) - 0.020f) < 0.000001f);
    config.thresholdV = 0.001f;
    assert(std::fabs(gld1LegacyTarget(-0.020f, config) - 0.010f) < 0.000001f);
    assert(std::fabs(gld1LegacyTarget(0.010f, config) - 0.015f) < 0.000001f);

    resetFake();
    auto all = runNullingService(ads, dac, logLine, nullptr, config);
    assert(all.status == GldNullingStatus::Ok && all.successCount == 8u);
    assert(baselineSteps == 8u * 11u && confirmSteps == 8u * 10u);
    assert(all.profile.dacCode[0] == 103u);
    assert(!hasLog("NULLING_STABILITY") && !hasLog("NULLING_CONFIRM_VERIFY") &&
           !hasLog("final_bump") && !hasLog("NULLING_EXP_BRACKET_REJECT"));

    resetFake();
    maxOnlyCrossing = true;
    uint16_t low = 0;
    uint16_t high = 0;
    assert(gld1LegacyFindRange(ads, dac, 0, 0.015f, low, high, logLine, nullptr));
    assert(high == board::GLD_DAC_CODE_MAX && hasLog("code=4095"));
    assert(hasLog("NULLING_EXP_STEP ch=0 sensor=MQ8 code=1 ") &&
           hasLog("NULLING_EXP_STEP ch=0 sensor=MQ8 code=2 ") &&
           hasLog("NULLING_EXP_STEP ch=0 sensor=MQ8 code=4 ") &&
           hasLog("NULLING_EXP_STEP ch=0 sensor=MQ8 code=8 ") &&
           hasLog("NULLING_EXP_STEP ch=0 sensor=MQ8 code=2048 ") &&
           !hasLog("NULLING_EXP_STEP ch=0 sensor=MQ8 code=3 "));

    resetFake();
    maxOnlyCrossing = true;
    saturateAt2048 = true;
    low = high = 0;
    assert(gld1LegacyFindRange(ads, dac, 0, 0.015f, low, high, logLine, nullptr));
    assert(low == 1024u && high == 2048u && hasLog("upper=saturated") &&
           !hasLog("stage=exponential reason=adc_invalid"));

    resetFake();
    uint16_t selected = 0;
    assert(gld1LegacyBinarySearch(ads, dac, 0, 0.015f, 63, 127, selected,
                                  logLine, nullptr));
    assert(selected == 100u);
    float chosenVoltage = 0.0f;
    assert(gld1LegacyConfirm(ads, dac, 0, 0.010f, 0.015f, selected, selected,
                             chosenVoltage, logLine, nullptr, config));
    assert(selected == 103u && confirmSteps == 10u &&
           std::fabs(chosenVoltage - 0.0151f) < 0.000001f);

    resetFake();
    negativeBaseline = true;
    selected = 100;
    assert(gld1LegacyConfirm(ads, dac, 0, -0.020f, 0.010f, selected, selected,
                             chosenVoltage, logLine, nullptr, config));
    assert(selected == 102u && confirmSteps == 20u &&
           std::fabs(chosenVoltage - 0.0102f) < 0.000001f);

    resetFake();
    negativeBaseline = true;
    const ChannelResult negativeResult = nullOneChannelGld1Legacy(
        ads, dac, 0, logLine, nullptr, config);
    assert(negativeResult.success && negativeResult.dacCode == 102u &&
           negativeResult.afterV >= 0.010f);

    resetFake();
    badSampleChannel = 3;
    all = runNullingService(ads, dac, logLine, nullptr, config);
    assert(all.status == GldNullingStatus::PartialSuccess && all.successCount == 7u);
    assert(all.profile.channelOk[3] == 0u && !isNullingProfileValid(all.profile));

    std::puts("PASS: GLD1 deterministic legacy nulling: exact samples, 2048 exp, binary, 10/20 confirm, minimum overshoot, and 8/8 profile gate");
    return 0;
#endif
}
