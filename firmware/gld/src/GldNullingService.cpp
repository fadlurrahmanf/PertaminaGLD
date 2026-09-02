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
// The MQ bridge can cross its clipped-baseline region within a narrow DAC
// interval.  Preserve exponential expansion at the start, then cap its
// increment so the 511-to-1023 type of jump cannot skip that transition.
constexpr uint16_t EXP_MAX_STEP         = 64;
// Do not let an early, noise-sized DAC response create an exponential bracket.
// Binary refinement may still choose below this code; this is a gate on the
// bracket-search phase only, not an absolute final-DAC floor.
constexpr uint16_t EXP_MIN_BRACKET_DAC  = 100;
constexpr uint8_t  CONFIRM_SIDE_SAMPLES = 10;
// Confirm scans the remaining verified exponential bracket, plus a small
// lower shoulder around the binary candidate. With EXP_MAX_STEP=64 this is
// bounded to 75 candidates, not an unbounded linear extension.
constexpr uint16_t CONFIRM_CANDIDATE_CAPACITY =
    EXP_MAX_STEP + CONFIRM_SIDE_SAMPLES + 1;
constexpr uint8_t  FINAL_CHECK_MAX_BUMPS = 20;
// MQ bridge/INA/ADS measurements continue to settle after a MCP4725 code
// change.  A single early sample can therefore bracket a transient rather
// than the real zero crossing.  Keep the existing four-stage algorithm, but
// make every decision from a small time-separated stability window.
constexpr uint32_t SETTLE_MS               = 150;
constexpr uint32_t STABILITY_SAMPLE_GAP_MS = 50;
constexpr uint8_t  STABILITY_WINDOW_COUNT  = 3;
constexpr uint32_t STABILITY_MAX_OBSERVE_MS = 3000;
// Large MCP4725 jumps can leave the MQ bridge/INA path in a long transient.
// Keep the mandated nulling stages, but travel to each requested DAC point in
// bounded increments so the observation starts from a controlled transition.
constexpr uint16_t DAC_RAMP_STEP             = 64;
constexpr uint32_t DAC_RAMP_STEP_DELAY_MS    = 25;
constexpr uint8_t  STABLE_GAIN_SAMPLES  = 3;
constexpr uint8_t  MAX_AVERAGE_ATTEMPTS = AVG_COUNT + 16;
constexpr float    BASELINE_THRESHOLD_RATIO = 0.5f;
constexpr float    BASELINE_NOISE_MULTIPLIER = 3.0f;
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
    float   spreadV;
    bool    stable;
    uint32_t observeMs;
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

bool writeDacRamped(GldDacMux& dac, uint8_t ch, uint16_t target,
                    GldNullingTickFn tickFn) {
    uint16_t current = dac.lastValue(ch);
    if (current < target) {
        while (static_cast<uint32_t>(target) - current > DAC_RAMP_STEP) {
            current = static_cast<uint16_t>(current + DAC_RAMP_STEP);
            if (!dac.writeDac(ch, current)) return false;
            pauseForMonitor(tickFn, DAC_RAMP_STEP_DELAY_MS);
        }
    } else {
        while (static_cast<uint32_t>(current) - target > DAC_RAMP_STEP) {
            current = static_cast<uint16_t>(current - DAC_RAMP_STEP);
            if (!dac.writeDac(ch, current)) return false;
            pauseForMonitor(tickFn, DAC_RAMP_STEP_DELAY_MS);
        }
    }
    return dac.writeDac(ch, target);
}

void emitStability(GldNullingLogFn logFn, const char* stage, uint8_t ch,
                   uint16_t code, const Snapshot& sample) {
    emitLog(logFn, "NULLING_STABILITY stage=%s ch=%u sensor=%s code=%u stable=%u spread=%.9f observeMs=%lu",
            stage, static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(code), sample.stable ? 1u : 0u, sample.spreadV,
            static_cast<unsigned long>(sample.observeMs));
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
            accepted == count, 0.0f, accepted == count, 0};
}

float medianOf(float* values, uint8_t count) {
    for (uint8_t i = 1; i < count; ++i) {
        const float value = values[i];
        uint8_t j = i;
        while (j > 0 && values[j - 1] > value) {
            values[j] = values[j - 1];
            --j;
        }
        values[j] = value;
    }
    return values[count / 2u];
}

float adaptiveStabilityToleranceV(const float* spreads, uint8_t count,
                                  float& medianSpreadV, float& madSpreadV) {
    float ordered[11]{};
    for (uint8_t i = 0; i < count; ++i) ordered[i] = spreads[i];
    medianSpreadV = medianOf(ordered, count);
    float deviations[11]{};
    for (uint8_t i = 0; i < count; ++i) {
        deviations[i] = fabsf(spreads[i] - medianSpreadV);
    }
    madSpreadV = medianOf(deviations, count);
    // Each board/channel derives its own band from the baseline's temporal
    // spread.  The multiplier is a robust-noise confidence factor, not an
    // absolute voltage setting.  The fallback only covers an ideal zero-noise
    // calculation so the comparison remains meaningful.
    const float derived = medianSpreadV + 3.0f * madSpreadV;
    return derived > 0.0f ? derived : 0.000001f;
}

float effectiveThresholdForChannel(float baselineV, float stabilityToleranceV,
                                   const GldNullingConfig& config) {
    const float baselineTerm = fabsf(baselineV) * BASELINE_THRESHOLD_RATIO;
    const float noiseTerm = stabilityToleranceV * BASELINE_NOISE_MULTIPLIER;
    return fmaxf(config.thresholdV, fmaxf(baselineTerm, noiseTerm));
}

Snapshot readSettledAverage(GldAds1256Reader& ads, uint8_t ch, uint8_t count,
                            GldNullingTickFn tickFn,
                            float toleranceV) {
    Snapshot last{0.0f, false, 0.0f, false, 0};
    const uint32_t startedMs = millis();
    for (;;) {
        float values[STABILITY_WINDOW_COUNT]{};
        bool allValid = true;
        for (uint8_t i = 0; i < STABILITY_WINDOW_COUNT; ++i) {
            const Snapshot sample = readAverage(ads, ch, count, tickFn);
            if (!sample.valid) {
                allValid = false;
                break;
            }
            values[i] = sample.voltage;
            if (i + 1u < STABILITY_WINDOW_COUNT) {
                pauseForMonitor(tickFn, STABILITY_SAMPLE_GAP_MS);
            }
        }
        if (!allValid) {
            last = {0.0f, false, 0.0f, false, millis() - startedMs};
            if (last.observeMs >= STABILITY_MAX_OBSERVE_MS) return last;
            pauseForMonitor(tickFn, STABILITY_SAMPLE_GAP_MS);
            continue;
        }
        float low = values[0];
        float high = values[0];
        for (uint8_t i = 1; i < STABILITY_WINDOW_COUNT; ++i) {
            if (values[i] < low) low = values[i];
            if (values[i] > high) high = values[i];
        }
        // Median avoids letting one residual settling sample choose the DAC.
        if (values[0] > values[1]) { const float tmp = values[0]; values[0] = values[1]; values[1] = tmp; }
        if (values[1] > values[2]) { const float tmp = values[1]; values[1] = values[2]; values[2] = tmp; }
        if (values[0] > values[1]) { const float tmp = values[0]; values[0] = values[1]; values[1] = tmp; }
        last = {values[1], true, high - low, (high - low) <= toleranceV,
                millis() - startedMs};
        if (last.stable) return last;
        if (last.observeMs >= STABILITY_MAX_OBSERVE_MS) return last;
        pauseForMonitor(tickFn, STABILITY_SAMPLE_GAP_MS);
    }
    return last;
}

// First code at or above EXP_MIN_BRACKET_DAC that has cleared the zero-margin
// and risen from the measured baseline by the configured threshold.
bool findRange(GldAds1256Reader& ads, GldDacMux& dac,
                uint8_t ch, float baselineV,
                uint16_t& outLow, uint16_t& outHigh,
                GldNullingLogFn logFn, GldNullingTickFn tickFn,
                const GldNullingConfig& config, float stabilityToleranceV,
                uint16_t resumeFrom = 0) {
    uint16_t step     = resumeFrom == 0 ? EXP_INIT_STEP : EXP_MAX_STEP;
    uint16_t previous = resumeFrom;
    uint16_t current  = resumeFrom == 0
                            ? 1
                            : static_cast<uint16_t>(min<uint32_t>(
                                  static_cast<uint32_t>(resumeFrom) + step,
                                  board::GLD_DAC_CODE_MAX));
    if (resumeFrom != 0) {
        emitLog(logFn, "NULLING_EXP_RESUME ch=%u sensor=%s from=%u next=%u step=%u",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(resumeFrom), static_cast<unsigned>(current),
                static_cast<unsigned>(step));
    }
    emitLog(logFn, "NULLING_EXP_START ch=%u sensor=%s baseline=%.6f threshold=%.6f minFinalV=%.6f minBracketDac=%u",
            static_cast<unsigned>(ch), sensorName(ch), baselineV, config.thresholdV, config.minFinalV,
            static_cast<unsigned>(EXP_MIN_BRACKET_DAC));

    while (current <= board::GLD_DAC_CODE_MAX) {
        if (!writeDacRamped(dac, ch, current, tickFn)) {
            emitLog(logFn, "NULLING_EXP_WRITE_FAIL ch=%u sensor=%s code=%u",
                    static_cast<unsigned>(ch), sensorName(ch),
                    static_cast<unsigned>(current));
            return false;
        }
        settle(tickFn);
        const Snapshot snap = readSettledAverage(ads, ch, AVG_COUNT, tickFn, stabilityToleranceV);
        emitStability(logFn, "exp", ch, current, snap);
        const float delta = snap.voltage - baselineV;
        const bool zeroMargin = snap.voltage >= -config.thresholdV;
        const bool outBaseline = delta >= config.thresholdV;
        emitLog(logFn, "NULLING_EXP_STEP ch=%u sensor=%s code=%u voltage=%.6f delta=%.6f valid=%u zeroMargin=%u outBaseline=%u",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(current), snap.voltage, delta,
                snap.valid ? 1u : 0u, zeroMargin ? 1u : 0u, outBaseline ? 1u : 0u);
        // A bridge may legitimately be noisy while it first leaves the
        // clipped baseline.  Do not skip that first valid crossing solely on
        // temporal spread; spread remains logged for diagnosis, while the
        // same-gain averaged reading and the independent Confirm verify guard
        // the selected result.
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
                      const GldNullingConfig& config, float stabilityToleranceV) {
    emitLog(logFn, "NULLING_BIN_START ch=%u sensor=%s low=%u high=%u",
            static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(low), static_cast<unsigned>(high));

    while (low + 1 < high) {
        const uint16_t mid = static_cast<uint16_t>((low + high) / 2);
        const bool writeOk = writeDacRamped(dac, ch, mid, tickFn);
        settle(tickFn);
        const Snapshot snap = readSettledAverage(ads, ch, AVG_COUNT, tickFn, stabilityToleranceV);
        emitStability(logFn, "bin", ch, mid, snap);
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

// The first crossing seen by exponential search can be a transient sample.
// Re-read exactly that same high endpoint before allowing binary search to use
// its bracket.  A false crossing is handled by resuming exponential search
// after the endpoint, never by returning to DAC 0.
bool recheckExponentialCrossing(GldAds1256Reader& ads, GldDacMux& dac,
                                uint8_t ch, float baselineV, uint16_t high,
                                GldNullingLogFn logFn, GldNullingTickFn tickFn,
                                const GldNullingConfig& config,
                                float stabilityToleranceV) {
    const bool writeOk = writeDacRamped(dac, ch, high, tickFn);
    settle(tickFn);
    const Snapshot snap = readSettledAverage(ads, ch, AVG_COUNT, tickFn, stabilityToleranceV);
    emitStability(logFn, "exp_recheck", ch, high, snap);
    const float delta = snap.voltage - baselineV;
    const bool zeroMargin = snap.voltage >= -config.thresholdV;
    const bool outBaseline = delta >= config.thresholdV;
    const bool passed = writeOk && snap.valid && zeroMargin && outBaseline;
    emitLog(logFn, "NULLING_EXP_RECHECK ch=%u sensor=%s code=%u voltage=%.9f delta=%.6f valid=%u zeroMargin=%u outBaseline=%u write=%u passed=%u",
            static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(high),
            snap.voltage, delta, snap.valid ? 1u : 0u, zeroMargin ? 1u : 0u,
            outBaseline ? 1u : 0u, writeOk ? 1u : 0u, passed ? 1u : 0u);
    return passed;
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
                 uint16_t bracketHigh,
                 GldNullingLogFn logFn, GldNullingTickFn tickFn,
                 const GldNullingConfig& config, float stabilityToleranceV) {
    int start = static_cast<int>(dacCode) - static_cast<int>(CONFIRM_SIDE_SAMPLES);
    int end = max<int>(static_cast<int>(dacCode) + static_cast<int>(CONFIRM_SIDE_SAMPLES),
                       static_cast<int>(bracketHigh));
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
    Candidate positives[CONFIRM_CANDIDATE_CAPACITY];
    int positiveCount = 0;
    bool haveFallback = false;
    uint16_t fallbackCode = 0;
    float fallbackVoltage = 0.0f;
    for (int code = start; code <= end; ++code) {
        const bool writeOk = writeDacRamped(dac, ch, static_cast<uint16_t>(code), tickFn);
        settle(tickFn);
        const Snapshot snap = readSettledAverage(ads, ch, CONFIRM_COUNT, tickFn, stabilityToleranceV);
        emitStability(logFn, "confirm", ch, static_cast<uint16_t>(code), snap);
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
        if (snap.voltage >= 0.0f && positiveCount < CONFIRM_CANDIDATE_CAPACITY) {
            positives[positiveCount++] = {static_cast<uint16_t>(code), snap.voltage};
        }
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
        if (!writeDacRamped(dac, ch, candidate, tickFn)) {
            positives[bestIdx] = positives[positiveCount - 1];
            --positiveCount;
            continue;
        }
        settle(tickFn);
        const Snapshot verify = readSettledAverage(ads, ch, AVG_COUNT, tickFn, stabilityToleranceV);
        emitStability(logFn, "verify", ch, candidate, verify);
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

    const bool zeroWriteOk = writeDacRamped(dac, ch, 0, tickFn);
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
    float baselineSpreads[11]{};
    uint8_t baselineCount = 0;
    for (uint16_t code = 0; code <= BASELINE_PRESCAN_MAX; ++code) {
        const bool writeOk = writeDacRamped(dac, ch, code, tickFn);
        settle(tickFn);
        // Baseline intentionally records the observed spread before deciding
        // the channel's own stability limit; do not apply a global gate here.
        const Snapshot sample = readSettledAverage(ads, ch, AVG_COUNT, tickFn, 1.0e9f);
        emitStability(logFn, "baseline", ch, code, sample);
        emitLog(logFn, "NULLING_BASELINE_STEP ch=%u sensor=%s code=%u voltage=%.9f valid=%u write=%u",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(code),
                sample.voltage, sample.valid ? 1u : 0u, writeOk ? 1u : 0u);
        if (sample.valid) {
            baselineSum += sample.voltage;
            baselineSpreads[baselineCount] = sample.spreadV;
            ++baselineCount;
        }
    }
    if (baselineCount == 0) {
        r.errorCode = 2;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=baseline error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
        return r;
    }
    r.baselineV = baselineSum / static_cast<float>(baselineCount);
    float medianSpreadV = 0.0f;
    float madSpreadV = 0.0f;
    const float stabilityToleranceV = adaptiveStabilityToleranceV(
        baselineSpreads, baselineCount, medianSpreadV, madSpreadV);
    emitLog(logFn, "NULLING_BASELINE_DONE ch=%u sensor=%s baseline=%.6f validSamples=%u medianSpread=%.9f madSpread=%.9f stabilityTolerance=%.9f",
            static_cast<unsigned>(ch), sensorName(ch), r.baselineV,
            static_cast<unsigned>(baselineCount), medianSpreadV, madSpreadV, stabilityToleranceV);

    GldNullingConfig channelConfig = config;
    channelConfig.thresholdV = effectiveThresholdForChannel(
        r.baselineV, stabilityToleranceV, config);
    emitLog(logFn, "NULLING_THRESHOLD_DERIVED ch=%u sensor=%s effective=%.9f baselineTerm=%.9f noiseTerm=%.9f floor=%.9f ratio=%.3f noiseMultiplier=%.3f",
            static_cast<unsigned>(ch), sensorName(ch), channelConfig.thresholdV,
            fabsf(r.baselineV) * BASELINE_THRESHOLD_RATIO,
            stabilityToleranceV * BASELINE_NOISE_MULTIPLIER,
            config.thresholdV, BASELINE_THRESHOLD_RATIO, BASELINE_NOISE_MULTIPLIER);

    uint16_t low = 0;
    uint16_t high = 0;
    uint16_t resumeFrom = 0;
    emitStageTransition(logFn, ch, "baseline", "exponential");
    uint16_t selected = 0;
    while (true) {
        if (!findRange(ads, dac, ch, r.baselineV, low, high, logFn, tickFn, channelConfig,
                       stabilityToleranceV, resumeFrom)) {
            r.errorCode = 3;
            emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=exponential error=%u reason=%s",
                    static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(r.errorCode),
                    channelErrorName(r.errorCode));
            return r;
        }
        if (!recheckExponentialCrossing(ads, dac, ch, r.baselineV, high, logFn, tickFn,
                                        channelConfig, stabilityToleranceV)) {
            emitLog(logFn, "NULLING_EXP_BRACKET_REJECT ch=%u sensor=%s low=%u high=%u reason=recheck_failed",
                    static_cast<unsigned>(ch), sensorName(ch),
                    static_cast<unsigned>(low), static_cast<unsigned>(high));
            resumeFrom = high;
            continue;
        }
        emitStageTransition(logFn, ch, "exponential", "binary");
        selected = binarySearch(ads, dac, ch, r.baselineV, low, high, logFn, tickFn,
                                channelConfig, stabilityToleranceV);
        emitStageTransition(logFn, ch, "binary", "confirm");
        if (confirmCode(ads, dac, ch, r.baselineV, selected, high, logFn, tickFn,
                        channelConfig, stabilityToleranceV)) {
            break;
        }
        emitLog(logFn, "NULLING_CONFIRM_RESUME_EXP ch=%u sensor=%s low=%u high=%u selected=%u reason=confirm_failed",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(low), static_cast<unsigned>(high),
                static_cast<unsigned>(selected));
        resumeFrom = high;
        emitStageTransition(logFn, ch, "confirm", "exponential_resume");
    }

    if (!writeDacRamped(dac, ch, selected, tickFn)) {
        r.errorCode = 5;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=final_write error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(r.errorCode),
                channelErrorName(r.errorCode));
        return r;
    }
    settle(tickFn);
    Snapshot after = readSettledAverage(ads, ch, AVG_COUNT, tickFn, stabilityToleranceV);
    emitStability(logFn, "final", ch, selected, after);
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
    bool afterZeroMargin = after.voltage >= -channelConfig.thresholdV;
    while ((after.voltage < channelConfig.minFinalV || !afterZeroMargin || afterDelta < channelConfig.thresholdV) &&
           finalBumps < FINAL_CHECK_MAX_BUMPS &&
           selected < board::GLD_DAC_CODE_MAX) {
        ++selected;
        ++finalBumps;
        if (!writeDacRamped(dac, ch, selected, tickFn)) { r.errorCode = 5; return r; }
        settle(tickFn);
        after = readSettledAverage(ads, ch, AVG_COUNT, tickFn, stabilityToleranceV);
        emitStability(logFn, "final_bump", ch, selected, after);
        r.afterV = after.voltage;
        if (!after.valid) { r.errorCode = 6; return r; }
        afterDelta = after.voltage - r.baselineV;
        afterZeroMargin = after.voltage >= -channelConfig.thresholdV;
    }
    if (after.voltage < channelConfig.minFinalV || !afterZeroMargin || afterDelta < channelConfig.thresholdV) {
        r.errorCode = 7;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=final_check error=%u reason=%s after=%.9f delta=%.6f threshold=%.6f min=%.9f zeroMargin=%u bumps=%u",
                static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(r.errorCode),
                channelErrorName(r.errorCode), after.voltage, afterDelta, channelConfig.thresholdV, channelConfig.minFinalV,
                afterZeroMargin ? 1u : 0u, static_cast<unsigned>(finalBumps));
        return r;
    }
    r.dacCode  = selected;
    r.success  = true;
    r.errorCode = 0;
    emitLog(logFn, "NULLING_CH_OK ch=%u sensor=%s dac=%u baseline=%.6f after=%.9f delta=%.6f threshold=%.6f",
            static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(r.dacCode), r.baselineV, r.afterV, afterDelta, channelConfig.thresholdV);
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
    emitLog(logFn, "NULLING_SERVICE_START channels=%u channelMask=0x%02X avgCount=%u confirmCount=%u settleMs=%lu stabilityWindows=%u stabilityGapMs=%lu stability=adaptive_per_channel thresholdV=%.6f minFinalV=%.6f",
            static_cast<unsigned>(out.attemptedCount), static_cast<unsigned>(selectedMask),
            static_cast<unsigned>(AVG_COUNT),
            static_cast<unsigned>(CONFIRM_COUNT), static_cast<unsigned long>(SETTLE_MS),
            static_cast<unsigned>(STABILITY_WINDOW_COUNT), static_cast<unsigned long>(STABILITY_SAMPLE_GAP_MS),
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
