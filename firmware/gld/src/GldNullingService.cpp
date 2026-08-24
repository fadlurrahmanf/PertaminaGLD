#include "GldNullingService.h"

#include <Arduino.h>
#include <Preferences.h>

#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>

#include "BoardPins.h"

namespace pgl::gld {

namespace {

constexpr uint8_t  AVG_COUNT            = 8;
constexpr uint8_t  CONFIRM_COUNT        = 10;
constexpr uint16_t EXP_INIT_STEP        = 1;
constexpr uint16_t EXP_MAX_STEP         = 2048;
// Do not let an early, noise-sized DAC response create an exponential bracket.
// Binary refinement may still choose below this code; this is a gate on the
// bracket-search phase only, not an absolute final-DAC floor.
constexpr uint16_t EXP_MIN_BRACKET_DAC  = 100;
constexpr uint8_t  CONFIRM_SIDE_SAMPLES = 10;
// 10 below + the Binary result + 10 above. This deliberately exceeds the
// operator minimum of 20 Confirm points while retaining the Binary candidate.
constexpr uint8_t  CONFIRM_WINDOW_TOTAL = 2 * CONFIRM_SIDE_SAMPLES + 1;
constexpr uint8_t  FINAL_CHECK_MAX_BUMPS = 20;
constexpr uint32_t SETTLE_MS            = 5;
constexpr uint8_t  STABLE_GAIN_SAMPLES  = 3;
constexpr uint8_t  MAX_AVERAGE_ATTEMPTS = AVG_COUNT + 16;
// In external-power operation all MQ rails remain ON during nulling. The TCA
// alone isolates the selected MCP4725 I2C channel; cycling TPS22919 rails here
// would cool/restart the MQ bridge and invalidate the calibration samples.
constexpr uint32_t NULLING_ALL_SENSORS_WARMUP_MS = 30000;
// No deliberate pause between algorithm phases. The transition log is retained
// for the operator UI, while the per-write DAC/ADC settle remains separate.
constexpr uint32_t STAGE_TRANSITION_DELAY_MS = 0;

constexpr const char* NVS_NAMESPACE = "gld-null";
constexpr const char* NVS_KEY       = "profile";
constexpr const char* NVS_CONFIG_NAMESPACE = "gld-nullcfg";
constexpr const char* NVS_CONFIG_KEY       = "config";

struct Snapshot {
    float   voltage;
    bool    valid;
};

const char* sensorName(uint8_t ch) {
    return ch < board::SENSOR_COUNT ? board::SENSOR_NAMES[ch] : "?";
}

const char* channelErrorName(uint8_t errorCode) {
    switch (errorCode) {
        case 1: return "dac_zero_write_failed";
        case 2: return "baseline_no_valid_samples";
        case 3: return "exponential_range_not_found";
        case 4: return "confirm_failed";
        case 5: return "dac_final_write_failed";
        case 6: return "after_read_invalid";
        case 7: return "after_threshold_not_met";
        default: return "none";
    }
}

void emitLog(GldNullingLogFn logFn, const char* fmt, ...) {
    if (!logFn) return;
    char line[384];
    va_list args;
    va_start(args, fmt);
    vsnprintf(line, sizeof(line), fmt, args);
    va_end(args);
    logFn(line);
}

void serviceTick(GldNullingTickFn tickFn) {
    if (tickFn) tickFn();
}

void settle(GldNullingTickFn tickFn) {
    serviceTick(tickFn);
    delay(SETTLE_MS);
    serviceTick(tickFn);
}

// Chunked delay (ticks every 50ms) so WDT/serial stay serviced during the pause.
void pauseForMonitor(GldNullingTickFn tickFn, uint32_t durationMs = STAGE_TRANSITION_DELAY_MS) {
    uint32_t elapsed = 0;
    while (elapsed < durationMs) {
        serviceTick(tickFn);
        const uint32_t chunk = (durationMs - elapsed) > 50U ? 50U : (durationMs - elapsed);
        delay(chunk);
        elapsed += chunk;
    }
    serviceTick(tickFn);
}

// Keep the long external-power warmup observable in the Expert Console while
// preserving the 50 ms service tick cadence used for WDT and serial handling.
void warmupAllSensorsWithCountdown(GldNullingLogFn logFn, GldNullingTickFn tickFn) {
    constexpr uint32_t kCountdownStepMs = 1000;
    const uint32_t totalSeconds =
        (NULLING_ALL_SENSORS_WARMUP_MS + kCountdownStepMs - 1U) / kCountdownStepMs;
    emitLog(logFn, "NULLING_WARMUP_START totalSec=%lu",
            static_cast<unsigned long>(totalSeconds));
    for (uint32_t remainingSeconds = totalSeconds; remainingSeconds > 0; --remainingSeconds) {
        emitLog(logFn, "NULLING_WARMUP remainingSec=%lu",
                static_cast<unsigned long>(remainingSeconds));
        pauseForMonitor(tickFn, kCountdownStepMs);
    }
    emitLog(logFn, "NULLING_WARMUP_DONE");
}

void emitStageTransition(GldNullingLogFn logFn, uint8_t ch, const char* from, const char* to) {
    emitLog(logFn, "NULLING_STAGE_TRANSITION ch=%u sensor=%s from=%s to=%s pauseMs=%lu",
            static_cast<unsigned>(ch), sensorName(ch), from, to,
            static_cast<unsigned long>(STAGE_TRANSITION_DELAY_MS));
}

Snapshot readAverage(GldAds1256Reader& ads, uint8_t ch, uint8_t count,
                     GldNullingTickFn tickFn) {
    float sum = 0.0f;
    uint8_t accepted = 0;
    uint8_t stableGain = 0;
    uint8_t consecutiveSameGain = 0;
    for (uint8_t attempt = 0; attempt < MAX_AVERAGE_ATTEMPTS && accepted < count; ++attempt) {
        serviceTick(tickFn);
        const GldAds1256Reading r = ads.readChannel(ch);
        if (r.status != GldAds1256Status::Ok || r.saturated) {
            accepted = 0;
            consecutiveSameGain = 0;
            continue;
        }
        if (consecutiveSameGain == 0 || r.gain != stableGain) {
            stableGain = r.gain;
            consecutiveSameGain = 1;
            accepted = 0;
            sum = 0.0f;
            continue;
        }
        ++consecutiveSameGain;
        if (consecutiveSameGain < STABLE_GAIN_SAMPLES) continue;
        sum += r.voltage;
        ++accepted;
    }
    serviceTick(tickFn);
    return {accepted == count ? sum / static_cast<float>(count) : 0.0f,
            accepted == count};
}

// First code at or above EXP_MIN_BRACKET_DAC that has cleared the zero-margin
// and risen from the measured baseline by the configured threshold.
bool findRange(GldAds1256Reader& ads, GldDacMux& dac,
                uint8_t ch, float baselineV,
                uint16_t& outLow, uint16_t& outHigh,
                GldNullingLogFn logFn, GldNullingTickFn tickFn,
                const GldNullingConfig& config) {
    uint16_t step     = EXP_INIT_STEP;
    uint16_t previous = 0;
    uint16_t current  = 1;
    emitLog(logFn, "NULLING_EXP_START ch=%u sensor=%s baseline=%.6f threshold=%.6f minFinalV=%.6f minBracketDac=%u",
            static_cast<unsigned>(ch), sensorName(ch), baselineV, config.thresholdV, config.minFinalV,
            static_cast<unsigned>(EXP_MIN_BRACKET_DAC));

    while (current <= board::GLD_DAC_CODE_MAX) {
        if (!dac.writeDac(ch, current)) {
            emitLog(logFn, "NULLING_EXP_WRITE_FAIL ch=%u sensor=%s code=%u",
                    static_cast<unsigned>(ch), sensorName(ch),
                    static_cast<unsigned>(current));
            return false;
        }
        settle(tickFn);
        const Snapshot snap = readAverage(ads, ch, AVG_COUNT, tickFn);
        const float delta = snap.voltage - baselineV;
        const bool zeroMargin = snap.voltage >= -config.thresholdV;
        const bool outBaseline = delta >= config.thresholdV;
        emitLog(logFn, "NULLING_EXP_STEP ch=%u sensor=%s code=%u voltage=%.6f delta=%.6f valid=%u zeroMargin=%u outBaseline=%u",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(current), snap.voltage, delta,
                snap.valid ? 1u : 0u, zeroMargin ? 1u : 0u, outBaseline ? 1u : 0u);
        if (current >= EXP_MIN_BRACKET_DAC && snap.valid && zeroMargin && outBaseline) {
            outLow  = previous;
            outHigh = current;
            emitLog(logFn, "NULLING_EXP_RANGE ch=%u sensor=%s low=%u high=%u",
                    static_cast<unsigned>(ch), sensorName(ch),
                    static_cast<unsigned>(outLow), static_cast<unsigned>(outHigh));
            return true;
        }
        previous = current;
        step = static_cast<uint16_t>(
            min<uint32_t>(static_cast<uint32_t>(step) * 2U, EXP_MAX_STEP));
        const uint32_t next = static_cast<uint32_t>(current) + step;
        current = next > board::GLD_DAC_CODE_MAX
                      ? board::GLD_DAC_CODE_MAX
                      : static_cast<uint16_t>(next);
        if (previous == current) break;
    }
    emitLog(logFn, "NULLING_EXP_FAIL ch=%u sensor=%s lastCode=%u maxCode=%u",
            static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(previous),
            static_cast<unsigned>(board::GLD_DAC_CODE_MAX));
    return false;
}

uint16_t binarySearch(GldAds1256Reader& ads, GldDacMux& dac,
                      uint8_t ch, float baselineV,
                      uint16_t low, uint16_t high,
                      GldNullingLogFn logFn, GldNullingTickFn tickFn,
                      const GldNullingConfig& config) {
    emitLog(logFn, "NULLING_BIN_START ch=%u sensor=%s low=%u high=%u",
            static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(low), static_cast<unsigned>(high));

    while (low + 1 < high) {
        const uint16_t mid = static_cast<uint16_t>((low + high) / 2);
        const bool writeOk = dac.writeDac(ch, mid);
        settle(tickFn);
        const Snapshot snap = readAverage(ads, ch, AVG_COUNT, tickFn);
        const float delta = snap.voltage - baselineV;
        const bool zeroMargin = snap.voltage >= -config.thresholdV;
        const bool outBaseline = delta >= config.thresholdV;
        const bool passed = writeOk && snap.valid && zeroMargin && outBaseline;
        emitLog(logFn, "NULLING_BIN_STEP ch=%u sensor=%s low=%u high=%u mid=%u voltage=%.6f delta=%.6f valid=%u zeroMargin=%u outBaseline=%u write=%u",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(low),
                static_cast<unsigned>(high), static_cast<unsigned>(mid), snap.voltage, delta,
                snap.valid ? 1u : 0u, zeroMargin ? 1u : 0u, outBaseline ? 1u : 0u,
                writeOk ? 1u : 0u);
        if (passed) high = mid;
        else low = mid;
    }
    emitLog(logFn, "NULLING_BIN_DONE ch=%u sensor=%s selected=%u",
            static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(high));
    return high;
}

// Scans 10 DAC codes below and 10 above the binary-search boundary, including
// the boundary itself (21 points in total), then picks the first stable,
// observable rise above the clipped baseline.
//
// Right at the threshold boundary, one DAC LSB step can swing the reading by
// several hundred microvolts to a few millivolts, so the single code closest
// to the target can flip back below threshold on a fresh read. Each candidate
// is therefore re-verified with an independent read before being accepted.
bool confirmCode(GldAds1256Reader& ads, GldDacMux& dac,
                 uint8_t ch, float baselineV, uint16_t& dacCode,
                 GldNullingLogFn logFn, GldNullingTickFn tickFn,
                 const GldNullingConfig& config) {
    int start = static_cast<int>(dacCode) - static_cast<int>(CONFIRM_SIDE_SAMPLES);
    int end = static_cast<int>(dacCode) + static_cast<int>(CONFIRM_SIDE_SAMPLES);
    if (start < board::GLD_DAC_CODE_MIN) {
        end += board::GLD_DAC_CODE_MIN - start;
        start = board::GLD_DAC_CODE_MIN;
    }
    if (end > board::GLD_DAC_CODE_MAX) {
        start -= end - board::GLD_DAC_CODE_MAX;
        end = board::GLD_DAC_CODE_MAX;
        start = max<int>(board::GLD_DAC_CODE_MIN, start);
    }
    const int belowCount = static_cast<int>(dacCode) - start;
    const int aboveCount = end - static_cast<int>(dacCode);
    emitLog(logFn, "NULLING_CONFIRM_START ch=%u sensor=%s selected=%u start=%d end=%d samples=%d below=%d above=%d baseline=%.6f threshold=%.6f minFinalV=%.6f",
            static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(dacCode), start, end,
            end - start + 1, belowCount, aboveCount, baselineV, config.thresholdV, config.minFinalV);

    struct Candidate { uint16_t code; float voltage; };
    Candidate positives[CONFIRM_WINDOW_TOTAL];
    int positiveCount = 0;
    bool haveFallback = false;
    uint16_t fallbackCode = 0;
    float fallbackVoltage = 0.0f;
    for (int code = start; code <= end; ++code) {
        const bool writeOk = dac.writeDac(ch, static_cast<uint16_t>(code));
        settle(tickFn);
        const Snapshot snap = readAverage(ads, ch, CONFIRM_COUNT, tickFn);
        const float delta = snap.voltage - baselineV;
        const bool aboveMin = snap.voltage >= config.minFinalV;
        const bool zeroMargin = snap.voltage >= -config.thresholdV;
        const bool outBaseline = delta >= config.thresholdV;
        emitLog(logFn, "NULLING_CONFIRM_STEP ch=%u sensor=%s code=%d voltage=%.9f delta=%.6f valid=%u aboveMin=%u zeroMargin=%u outBaseline=%u write=%u",
                static_cast<unsigned>(ch), sensorName(ch), code, snap.voltage, delta,
                snap.valid ? 1u : 0u, aboveMin ? 1u : 0u, zeroMargin ? 1u : 0u,
                outBaseline ? 1u : 0u,
                writeOk ? 1u : 0u);
        if (!writeOk || !snap.valid || !zeroMargin || !outBaseline || !aboveMin) continue;
        if (snap.voltage >= 0.0f) positives[positiveCount++] = {static_cast<uint16_t>(code), snap.voltage};
        else if (!haveFallback || snap.voltage > fallbackVoltage) {
            fallbackCode = static_cast<uint16_t>(code);
            fallbackVoltage = snap.voltage;
            haveFallback = true;
        }
    }
    while (positiveCount > 0) {
        int bestIdx = 0;
        for (int i = 1; i < positiveCount; ++i) {
            if (positives[i].voltage < positives[bestIdx].voltage) bestIdx = i;
        }
        const uint16_t candidate = positives[bestIdx].code;
        dac.writeDac(ch, candidate);
        settle(tickFn);
        const Snapshot verify = readAverage(ads, ch, AVG_COUNT, tickFn);
        const float verifyDelta = verify.voltage - baselineV;
        const bool verifyAboveMin = verify.voltage >= config.minFinalV;
        const bool verifyZeroMargin = verify.voltage >= -config.thresholdV;
        const bool verifyOutBaseline = verifyDelta >= config.thresholdV;
        emitLog(logFn, "NULLING_CONFIRM_VERIFY ch=%u sensor=%s code=%u voltage=%.9f delta=%.6f valid=%u aboveMin=%u zeroMargin=%u outBaseline=%u",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(candidate),
                verify.voltage, verifyDelta, verify.valid ? 1u : 0u,
                verifyAboveMin ? 1u : 0u, verifyZeroMargin ? 1u : 0u,
                verifyOutBaseline ? 1u : 0u);
        if (verify.valid && verifyAboveMin && verifyZeroMargin && verifyOutBaseline) {
            dacCode = candidate;
            emitLog(logFn, "NULLING_CONFIRM_OK ch=%u sensor=%s code=%u voltage=%.9f mode=positive_verified",
                    static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(dacCode), verify.voltage);
            return true;
        }
        positives[bestIdx] = positives[positiveCount - 1];
        --positiveCount;
    }
    if (haveFallback) {
        dacCode = fallbackCode;
        emitLog(logFn, "NULLING_CONFIRM_OK ch=%u sensor=%s code=%u voltage=%.9f mode=fallback_above_min",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(dacCode), fallbackVoltage);
        return true;
    }
    emitLog(logFn, "NULLING_CONFIRM_FAIL ch=%u sensor=%s", static_cast<unsigned>(ch), sensorName(ch));
    return false;
}

struct ChannelResult {
    uint16_t dacCode;
    float    baselineV;
    float    afterV;
    bool     success;
    uint8_t  errorCode;
};

ChannelResult nullOneChannel(GldAds1256Reader& ads, GldDacMux& dac,
                             uint8_t ch, GldNullingLogFn logFn,
                             GldNullingTickFn tickFn,
                             const GldNullingConfig& config) {
    ChannelResult r{};
    r.success = false;
    emitLog(logFn, "NULLING_CH_START ch=%u sensor=%s",
            static_cast<unsigned>(ch), sensorName(ch));

    const bool zeroWriteOk = dac.writeDac(ch, 0);
    emitLog(logFn, "NULLING_MCP_WRITE ch=%u sensor=%s mux=%u address=0x%02X code=0 ack=%u source=zero",
            static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(board::SENSOR_TO_MUX_CH[ch]),
            static_cast<unsigned>(board::MCP4725_ADDR), zeroWriteOk ? 1u : 0u);
    if (!zeroWriteOk) {
        r.errorCode = 1;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=zero error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
        return r;
    }
    settle(tickFn);

    constexpr uint16_t BASELINE_PRESCAN_MAX = 10;
    emitLog(logFn, "NULLING_BASELINE_START ch=%u sensor=%s codeMin=%u codeMax=%u avgCount=%u",
            static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(board::GLD_DAC_CODE_MIN),
            static_cast<unsigned>(BASELINE_PRESCAN_MAX), static_cast<unsigned>(AVG_COUNT));
    float baselineSum = 0.0f;
    uint8_t baselineCount = 0;
    for (uint16_t code = 0; code <= BASELINE_PRESCAN_MAX; ++code) {
        const bool writeOk = dac.writeDac(ch, code);
        settle(tickFn);
        const Snapshot sample = readAverage(ads, ch, AVG_COUNT, tickFn);
        emitLog(logFn, "NULLING_BASELINE_STEP ch=%u sensor=%s code=%u voltage=%.9f valid=%u write=%u",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(code),
                sample.voltage, sample.valid ? 1u : 0u, writeOk ? 1u : 0u);
        if (sample.valid) { baselineSum += sample.voltage; ++baselineCount; }
    }
    if (baselineCount == 0) {
        r.errorCode = 2;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=baseline error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
        return r;
    }
    r.baselineV = baselineSum / static_cast<float>(baselineCount);
    emitLog(logFn, "NULLING_BASELINE_DONE ch=%u sensor=%s baseline=%.6f validSamples=%u",
            static_cast<unsigned>(ch), sensorName(ch), r.baselineV,
            static_cast<unsigned>(baselineCount));

    uint16_t low = 0;
    uint16_t high = 0;
    emitStageTransition(logFn, ch, "baseline", "exponential");
    if (!findRange(ads, dac, ch, r.baselineV, low, high, logFn, tickFn, config)) {
        r.errorCode = 3;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=exponential error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(r.errorCode),
                channelErrorName(r.errorCode));
        return r;
    }
    emitStageTransition(logFn, ch, "exponential", "binary");
    uint16_t selected = binarySearch(ads, dac, ch, r.baselineV, low, high, logFn, tickFn, config);
    emitStageTransition(logFn, ch, "binary", "confirm");
    if (!confirmCode(ads, dac, ch, r.baselineV, selected, logFn, tickFn, config)) {
        r.errorCode = 4;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=confirm error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(r.errorCode),
                channelErrorName(r.errorCode));
        return r;
    }

    if (!dac.writeDac(ch, selected)) {
        r.errorCode = 5;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=final_write error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(r.errorCode),
                channelErrorName(r.errorCode));
        return r;
    }
    settle(tickFn);
    Snapshot after = readAverage(ads, ch, AVG_COUNT, tickFn);
    r.afterV = after.voltage;
    if (!after.valid) {
        r.errorCode = 6;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=after_read error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(r.errorCode),
                channelErrorName(r.errorCode));
        return r;
    }
    uint8_t finalBumps = 0;
    float afterDelta = after.voltage - r.baselineV;
    bool afterZeroMargin = after.voltage >= -config.thresholdV;
    while ((after.voltage < config.minFinalV || !afterZeroMargin || afterDelta < config.thresholdV) &&
           finalBumps < FINAL_CHECK_MAX_BUMPS &&
           selected < board::GLD_DAC_CODE_MAX) {
        ++selected;
        ++finalBumps;
        if (!dac.writeDac(ch, selected)) { r.errorCode = 5; return r; }
        settle(tickFn);
        after = readAverage(ads, ch, AVG_COUNT, tickFn);
        r.afterV = after.voltage;
        if (!after.valid) { r.errorCode = 6; return r; }
        afterDelta = after.voltage - r.baselineV;
        afterZeroMargin = after.voltage >= -config.thresholdV;
    }
    if (after.voltage < config.minFinalV || !afterZeroMargin || afterDelta < config.thresholdV) {
        r.errorCode = 7;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=final_check error=%u reason=%s after=%.9f delta=%.6f threshold=%.6f min=%.9f zeroMargin=%u bumps=%u",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(r.errorCode),
                channelErrorName(r.errorCode), after.voltage, afterDelta, config.thresholdV, config.minFinalV,
                afterZeroMargin ? 1u : 0u, static_cast<unsigned>(finalBumps));
        return r;
    }
    r.dacCode  = selected;
    r.success  = true;
    r.errorCode = 0;
    emitLog(logFn, "NULLING_CH_OK ch=%u sensor=%s dac=%u baseline=%.6f after=%.9f delta=%.6f threshold=%.6f",
            static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(r.dacCode), r.baselineV, r.afterV, afterDelta, config.thresholdV);
    return r;
}

}  // namespace

GldNullingServiceResult runNullingService(GldAds1256Reader& ads,
                                          GldDacMux& dac,
                                          GldNullingLogFn logFn,
                                          GldNullingTickFn tickFn,
                                          const GldNullingConfig& config,
                                          uint8_t channelMask) {
    GldNullingServiceResult out{};
    out.status = GldNullingStatus::Ok;

    const uint8_t validMask = static_cast<uint8_t>((1u << board::SENSOR_COUNT) - 1u);
    const uint8_t selectedMask = static_cast<uint8_t>(channelMask & validMask);
    for (uint8_t ch = 0; ch < board::SENSOR_COUNT; ++ch) {
        if ((selectedMask & static_cast<uint8_t>(1u << ch)) != 0u) ++out.attemptedCount;
    }

    out.profile.algorithmVersion = NULLING_PROFILE_ALGORITHM_VERSION;
    emitLog(logFn, "NULLING_SERVICE_START channels=%u channelMask=0x%02X avgCount=%u confirmCount=%u settleMs=%lu thresholdV=%.6f minFinalV=%.6f",
            static_cast<unsigned>(out.attemptedCount), static_cast<unsigned>(selectedMask),
            static_cast<unsigned>(AVG_COUNT),
            static_cast<unsigned>(CONFIRM_COUNT), static_cast<unsigned long>(SETTLE_MS),
            config.thresholdV, config.minFinalV);

    if (!ads.ready()) {
        serviceTick(tickFn);
        out.status = GldNullingStatus::AdsNotReady;
        emitLog(logFn, "NULLING_SERVICE_BLOCKED status=%s", gldNullingStatusName(out.status));
        return out;
    }
    if (!dac.ready()) {
        serviceTick(tickFn);
        out.status = GldNullingStatus::DacNotReady;
        emitLog(logFn, "NULLING_SERVICE_BLOCKED status=%s", gldNullingStatusName(out.status));
        return out;
    }
    if (selectedMask == 0u) {
        out.status = GldNullingStatus::AllChannelsFailed;
        emitLog(logFn, "NULLING_SERVICE_BLOCKED status=%s reason=no_channels_selected", gldNullingStatusName(out.status));
        return out;
    }

    // All sensor bridges warm up together before the caller begins its
    // board-specific DAC-write policy.  GLD2 may then isolate the active
    // module if an all-rails-on I2C path is not electrically reliable.
    emitLog(logFn, "NULLING_SENSOR_POWER_MODE=all_on_warmup_dac_policy=caller_managed warmupMs=%lu",
            static_cast<unsigned long>(NULLING_ALL_SENSORS_WARMUP_MS));
    warmupAllSensorsWithCountdown(logFn, tickFn);

    uint8_t successes = 0;
    for (uint8_t ch = 0; ch < board::SENSOR_COUNT; ++ch) {
        if ((selectedMask & static_cast<uint8_t>(1u << ch)) == 0u) continue;
        serviceTick(tickFn);
        const ChannelResult cr = nullOneChannel(ads, dac, ch, logFn, tickFn, config);
        out.profile.dacCode[ch]   = cr.dacCode;
        out.profile.baselineV[ch] = cr.baselineV;
        out.profile.afterV[ch]    = cr.afterV;
        out.profile.channelOk[ch] = cr.success ? 1u : 0u;
        if (cr.success) ++successes;
    }

    out.successCount = successes;
    if (successes == 0) {
        out.status = GldNullingStatus::AllChannelsFailed;
    } else if (successes < out.attemptedCount) {
        out.status = GldNullingStatus::PartialSuccess;
    }
    emitLog(logFn, "NULLING_SENSOR_POWER_RESTORE=CALLER_MANAGED");
    emitLog(logFn, "NULLING_SERVICE_DONE status=%s successCount=%u/%u",
            gldNullingStatusName(out.status),
            static_cast<unsigned>(out.successCount),
            static_cast<unsigned>(out.attemptedCount));
    return out;
}

GldNullingSingleResult runNullingServiceSingleChannel(GldAds1256Reader& ads,
                                                      GldDacMux& dac,
                                                      uint8_t channel,
                                                      GldNullingLogFn logFn,
                                                      GldNullingTickFn tickFn,
                                                      const GldNullingConfig& config) {
    GldNullingSingleResult out{};
    out.status = GldNullingStatus::Ok;

    if (!ads.ready()) {
        serviceTick(tickFn);
        out.status = GldNullingStatus::AdsNotReady;
        emitLog(logFn, "NULLING_SERVICE_BLOCKED status=%s channel=%u", gldNullingStatusName(out.status), static_cast<unsigned>(channel));
        return out;
    }
    if (!dac.ready()) {
        serviceTick(tickFn);
        out.status = GldNullingStatus::DacNotReady;
        emitLog(logFn, "NULLING_SERVICE_BLOCKED status=%s channel=%u", gldNullingStatusName(out.status), static_cast<unsigned>(channel));
        return out;
    }

    serviceTick(tickFn);
    const ChannelResult cr = nullOneChannel(ads, dac, channel, logFn, tickFn, config);
    out.dacCode   = cr.dacCode;
    out.baselineV = cr.baselineV;
    out.afterV    = cr.afterV;
    out.success   = cr.success;
    out.status    = cr.success ? GldNullingStatus::Ok : GldNullingStatus::SingleChannelFailed;
    return out;
}

GldFullScaleSweepResult runFullScaleSweep(GldAds1256Reader& ads,
                                          GldDacMux& dac,
                                          uint8_t channel,
                                          uint16_t restoreCode,
                                          uint16_t stepSize,
                                          GldNullingLogFn logFn,
                                          GldNullingTickFn tickFn,
                                          GldFullScaleSweepCancelFn cancelFn) {
    GldFullScaleSweepResult out{};
    out.success = false;
    out.status = GldNullingStatus::Ok;
    out.restoredCode = restoreCode;

    if (!ads.ready()) {
        serviceTick(tickFn);
        out.status = GldNullingStatus::AdsNotReady;
        emitLog(logFn, "FULLSCALE_BLOCKED status=%s channel=%u", gldNullingStatusName(out.status), static_cast<unsigned>(channel));
        return out;
    }
    if (!dac.ready()) {
        serviceTick(tickFn);
        out.status = GldNullingStatus::DacNotReady;
        emitLog(logFn, "FULLSCALE_BLOCKED status=%s channel=%u", gldNullingStatusName(out.status), static_cast<unsigned>(channel));
        return out;
    }
    if (stepSize == 0) stepSize = 1;

    emitLog(logFn, "FULLSCALE_START ch=%u sensor=%s codeMin=%u codeMax=%u step=%u avgCount=%u",
            static_cast<unsigned>(channel), sensorName(channel),
            static_cast<unsigned>(board::GLD_DAC_CODE_MIN),
            static_cast<unsigned>(board::GLD_DAC_CODE_MAX),
            static_cast<unsigned>(stepSize),
            static_cast<unsigned>(AVG_COUNT));

    uint32_t code = board::GLD_DAC_CODE_MIN;
    bool anyValidSample = false;
    for (;;) {
        serviceTick(tickFn);
        if (cancelFn && cancelFn()) {
            const bool restoreOk = dac.writeDac(channel, restoreCode);
            settle(tickFn);
            out.cancelled = true;
            out.success = restoreOk;
            if (!restoreOk) out.status = GldNullingStatus::DacNotReady;
            emitLog(logFn, "FULLSCALE_CANCELLED ch=%u sensor=%s restoreCode=%u restoreOk=%u",
                    static_cast<unsigned>(channel), sensorName(channel),
                    static_cast<unsigned>(restoreCode), restoreOk ? 1u : 0u);
            return out;
        }
        const bool writeOk = dac.writeDac(channel, static_cast<uint16_t>(code));
        settle(tickFn);
        const Snapshot snap = readAverage(ads, channel, AVG_COUNT, tickFn);
        emitLog(logFn, "FULLSCALE_STEP ch=%u sensor=%s code=%u voltage=%.6f valid=%u write=%u",
                static_cast<unsigned>(channel), sensorName(channel),
                static_cast<unsigned>(code), snap.voltage,
                snap.valid ? 1u : 0u, writeOk ? 1u : 0u);
        if (writeOk && snap.valid) anyValidSample = true;

        if (code >= board::GLD_DAC_CODE_MAX) break;
        const uint32_t next = code + stepSize;
        code = next > board::GLD_DAC_CODE_MAX ? board::GLD_DAC_CODE_MAX : next;
    }

    const bool restoreOk = dac.writeDac(channel, restoreCode);
    settle(tickFn);
    out.success = anyValidSample && restoreOk;
    if (!anyValidSample) out.status = GldNullingStatus::SingleChannelFailed;
    emitLog(logFn, "FULLSCALE_DONE ch=%u sensor=%s status=%s restoreCode=%u restoreOk=%u",
            static_cast<unsigned>(channel), sensorName(channel),
            gldNullingStatusName(out.status), static_cast<unsigned>(restoreCode),
            restoreOk ? 1u : 0u);
    return out;
}

bool saveNullingProfile(const GldNullingProfile& profile) {
    Preferences prefs;
    if (!prefs.begin(NVS_NAMESPACE, false)) return false;
    const size_t written = prefs.putBytes(NVS_KEY, &profile, sizeof(profile));
    prefs.end();
    return written == sizeof(profile);
}

bool loadNullingProfile(GldNullingProfile& out) {
    Preferences prefs;
    if (!prefs.begin(NVS_NAMESPACE, true)) return false;
    const size_t read = prefs.getBytes(NVS_KEY, &out, sizeof(out));
    prefs.end();
    return read == sizeof(GldNullingProfile) && isNullingProfileValid(out);
}

bool saveNullingConfig(const GldNullingConfig& config) {
    Preferences prefs;
    if (!prefs.begin(NVS_CONFIG_NAMESPACE, false)) return false;
    const size_t written = prefs.putBytes(NVS_CONFIG_KEY, &config, sizeof(config));
    prefs.end();
    return written == sizeof(config);
}

bool loadNullingConfig(GldNullingConfig& out) {
    Preferences prefs;
    if (!prefs.begin(NVS_CONFIG_NAMESPACE, true)) return false;
    const size_t read = prefs.getBytes(NVS_CONFIG_KEY, &out, sizeof(out));
    prefs.end();
    if (read != sizeof(GldNullingConfig) || !isNullingConfigValid(out)) return false;
    return true;
}

const char* gldNullingStatusName(GldNullingStatus s) {
    switch (s) {
        case GldNullingStatus::Ok:               return "Ok";
        case GldNullingStatus::AdsNotReady:      return "AdsNotReady";
        case GldNullingStatus::DacNotReady:      return "DacNotReady";
        case GldNullingStatus::AllChannelsFailed:return "AllChannelsFailed";
        case GldNullingStatus::PartialSuccess:   return "PartialSuccess";
        case GldNullingStatus::SingleChannelFailed: return "SingleChannelFailed";
    }
    return "Unknown";
}

}  // namespace pgl::gld
