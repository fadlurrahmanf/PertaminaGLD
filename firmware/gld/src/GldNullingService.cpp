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
constexpr uint16_t BASELINE_PRESCAN_MAX = 10;
constexpr uint16_t EXP_INIT_STEP        = 1;
constexpr uint16_t EXP_MAX_STEP         = 2048;
constexpr uint8_t  CONFIRM_WINDOW       = 10;  // baseline >= 0: 5 before + 5 after selected
constexpr uint8_t  CONFIRM_WINDOW_BEFORE_WIDE = 10;  // baseline < 0: 10 before + 10 after selected
constexpr uint8_t  CONFIRM_WINDOW_WIDE  = 20;
// How many single-LSB DAC bumps the final check may try if a verified-positive
// confirm code still reads negative on the (separate) final verification read.
constexpr uint8_t  FINAL_CHECK_MAX_BUMPS = 20;
constexpr uint32_t SETTLE_MS            = 5;
// Deliberate pause between algorithm phases (baseline -> exponential ->
// binary search -> confirm) so an app polling/monitoring the serial log can
// keep up and show each phase instead of the whole channel flashing by.
constexpr uint32_t STAGE_TRANSITION_DELAY_MS = 2000;

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
        case 7: return "after_voltage_negative";
        default: return "none";
    }
}

void emitLog(GldNullingLogFn logFn, const char* fmt, ...) {
    if (!logFn) return;
    char line[224];
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

void emitStageTransition(GldNullingLogFn logFn, uint8_t ch, const char* from, const char* to) {
    emitLog(logFn, "NULLING_STAGE_TRANSITION ch=%u sensor=%s from=%s to=%s pauseMs=%lu",
            static_cast<unsigned>(ch), sensorName(ch), from, to,
            static_cast<unsigned long>(STAGE_TRANSITION_DELAY_MS));
}

Snapshot readAverage(GldAds1256Reader& ads, uint8_t ch, uint8_t count,
                     GldNullingTickFn tickFn) {
    float sum = 0.0f;
    bool valid = true;
    for (uint8_t i = 0; i < count; ++i) {
        serviceTick(tickFn);
        const GldAds1256Reading r = ads.readChannel(ch);
        sum += r.voltage;
        valid = valid && (r.status == GldAds1256Status::Ok);
    }
    serviceTick(tickFn);
    return {sum / static_cast<float>(count), valid};
}

// Searches for the DAC code where the reading first crosses up to (near) zero
// volts, i.e. voltage >= -thresholdV. Target is absolute zero, not baselineV:
// a channel whose baseline sits deep negative needs a big compensation swing
// before it reaches zero, and locking onto "delta from baseline exceeds
// thresholdV" (the old behavior) converges on noise-level wobble right next
// to baseline instead of the real crossing, which can be very far away in
// DAC-code terms. baselineV is only used for logging/diagnostics here.
bool findRange(GldAds1256Reader& ads, GldDacMux& dac,
               uint8_t ch, float baselineV,
               uint16_t& outLow, uint16_t& outHigh,
               GldNullingLogFn logFn, GldNullingTickFn tickFn,
               const GldNullingConfig& config) {
    uint16_t step     = EXP_INIT_STEP;
    uint16_t previous = 0;
    uint16_t current  = 1;
    emitLog(logFn, "NULLING_EXP_START ch=%u sensor=%s baseline=%.6f threshold=%.6f target=0.000000",
            static_cast<unsigned>(ch), sensorName(ch), baselineV, config.thresholdV);

    while (current <= board::GLD_DAC_CODE_MAX) {
        if (!dac.writeDac(ch, current)) {
            emitLog(logFn, "NULLING_EXP_WRITE_FAIL ch=%u sensor=%s code=%u",
                    static_cast<unsigned>(ch), sensorName(ch),
                    static_cast<unsigned>(current));
            return false;
        }
        settle(tickFn);
        const Snapshot snap = readAverage(ads, ch, AVG_COUNT, tickFn);
        const float delta = fabsf(snap.voltage - baselineV);
        emitLog(logFn, "NULLING_EXP_STEP ch=%u sensor=%s code=%u voltage=%.6f delta=%.6f valid=%u",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(current), snap.voltage, delta,
                snap.valid ? 1u : 0u);
        if (snap.valid && snap.voltage >= -config.thresholdV) {
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

// Narrows to the precise code where voltage first crosses -thresholdV (same
// absolute-zero target as findRange, not baselineV).
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
        const float delta = fabsf(snap.voltage - baselineV);
        emitLog(logFn, "NULLING_BIN_STEP ch=%u sensor=%s low=%u high=%u mid=%u voltage=%.6f delta=%.6f valid=%u write=%u",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(low), static_cast<unsigned>(high),
                static_cast<unsigned>(mid), snap.voltage, delta,
                snap.valid ? 1u : 0u, writeOk ? 1u : 0u);
        if (snap.voltage < -config.thresholdV) {
            low = mid;
        } else {
            high = mid;
        }
    }
    emitLog(logFn, "NULLING_BIN_DONE ch=%u sensor=%s selected=%u",
            static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(high));
    return high;
}

// Scans a window of DAC codes around the binary-search boundary and picks the
// best confirmed code: prefer the code whose residual voltage is non-negative
// and closest to zero (headroom for gas detection above true zero). Baseline
// < 0 channels get a wider window (10 codes before + 10 after the binary
// search result, 20 total) because the code that first crosses into positive
// territory can sit further from the boundary than a baseline >= 0 channel
// needs.
//
// Right at the zero crossing, one DAC LSB step can swing the reading by
// several hundred microvolts to a few millivolts, so the single code closest
// to zero can flip sign on a fresh read (a different 8/10-sample average
// landing on the other side of the noise floor). Each positive candidate is
// therefore re-verified with an independent read before being accepted;
// candidates that fail to reconfirm are discarded and the next-closest
// positive candidate is tried, smallest first. If no candidate reconfirms
// non-negative, falls back to the first code that at least clears the
// configured minFinalV (old behavior), so a permissive minFinalV still works
// as an escape hatch.
bool confirmCode(GldAds1256Reader& ads, GldDacMux& dac,
                 uint8_t ch, float baselineV, uint16_t& dacCode,
                 GldNullingLogFn logFn, GldNullingTickFn tickFn,
                 const GldNullingConfig& config) {
    const bool wideSearch = baselineV < 0.0f;
    const int windowBefore = wideSearch ? static_cast<int>(CONFIRM_WINDOW_BEFORE_WIDE)
                                         : static_cast<int>(CONFIRM_WINDOW) / 2;
    const int windowSize = wideSearch ? static_cast<int>(CONFIRM_WINDOW_WIDE)
                                       : static_cast<int>(CONFIRM_WINDOW);

    int start = static_cast<int>(dacCode) - windowBefore;
    if (start < board::GLD_DAC_CODE_MIN) start = board::GLD_DAC_CODE_MIN;
    int end = start + windowSize - 1;
    if (end > board::GLD_DAC_CODE_MAX) {
        end   = board::GLD_DAC_CODE_MAX;
        start = max<int>(board::GLD_DAC_CODE_MIN, end - windowSize + 1);
    }
    emitLog(logFn, "NULLING_CONFIRM_START ch=%u sensor=%s start=%d end=%d minFinalV=%.6f wide=%u",
            static_cast<unsigned>(ch), sensorName(ch), start, end, config.minFinalV,
            wideSearch ? 1u : 0u);

    struct Candidate { uint16_t code; float voltage; };
    Candidate positives[CONFIRM_WINDOW_WIDE];
    int positiveCount = 0;
    bool haveFallback = false;
    uint16_t fallbackCode = 0;
    float fallbackVoltage = 0.0f;

    for (int code = start; code <= end; ++code) {
        const bool writeOk = dac.writeDac(ch, static_cast<uint16_t>(code));
        settle(tickFn);
        const Snapshot snap = readAverage(ads, ch, CONFIRM_COUNT, tickFn);
        const float delta = fabsf(snap.voltage - baselineV);
        const bool aboveMin = snap.voltage >= config.minFinalV;
        emitLog(logFn, "NULLING_CONFIRM_STEP ch=%u sensor=%s code=%d voltage=%.9f delta=%.6f valid=%u aboveMin=%u write=%u",
                static_cast<unsigned>(ch), sensorName(ch), code,
                snap.voltage, delta, snap.valid ? 1u : 0u,
                aboveMin ? 1u : 0u, writeOk ? 1u : 0u);

        if (!writeOk || !snap.valid) continue;

        if (snap.voltage >= 0.0f) {
            if (positiveCount < static_cast<int>(CONFIRM_WINDOW_WIDE)) {
                positives[positiveCount++] = {static_cast<uint16_t>(code), snap.voltage};
            }
        } else if (aboveMin && (!haveFallback || snap.voltage > fallbackVoltage)) {
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
        const uint16_t candidateCode = positives[bestIdx].code;

        dac.writeDac(ch, candidateCode);
        settle(tickFn);
        const Snapshot verify = readAverage(ads, ch, AVG_COUNT, tickFn);
        emitLog(logFn, "NULLING_CONFIRM_VERIFY ch=%u sensor=%s code=%u voltage=%.9f valid=%u",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(candidateCode), verify.voltage, verify.valid ? 1u : 0u);

        if (verify.valid && verify.voltage >= 0.0f) {
            dacCode = candidateCode;
            emitLog(logFn, "NULLING_CONFIRM_OK ch=%u sensor=%s code=%u voltage=%.9f mode=positive_verified",
                    static_cast<unsigned>(ch), sensorName(ch),
                    static_cast<unsigned>(dacCode), verify.voltage);
            return true;
        }

        // Didn't reconfirm - drop it and try the next-closest-to-zero candidate.
        positives[bestIdx] = positives[positiveCount - 1];
        --positiveCount;
    }

    if (haveFallback) {
        dacCode = fallbackCode;
        emitLog(logFn, "NULLING_CONFIRM_OK ch=%u sensor=%s code=%u voltage=%.9f mode=fallback_above_min",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(dacCode), fallbackVoltage);
        return true;
    }

    emitLog(logFn, "NULLING_CONFIRM_FAIL ch=%u sensor=%s",
            static_cast<unsigned>(ch), sensorName(ch));
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

    if (!dac.writeDac(ch, 0)) {
        r.errorCode = 1;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=zero error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
        return r;
    }
    settle(tickFn);

    emitLog(logFn, "NULLING_BASELINE_START ch=%u sensor=%s codeMin=%u codeMax=%u avgCount=%u",
            static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(board::GLD_DAC_CODE_MIN),
            static_cast<unsigned>(BASELINE_PRESCAN_MAX),
            static_cast<unsigned>(AVG_COUNT));
    float baselineSum  = 0.0f;
    uint8_t baseCount  = 0;
    for (uint16_t code = 0; code <= BASELINE_PRESCAN_MAX; ++code) {
        const bool writeOk = dac.writeDac(ch, code);
        settle(tickFn);
        const Snapshot s = readAverage(ads, ch, AVG_COUNT, tickFn);
        emitLog(logFn, "NULLING_BASELINE_STEP ch=%u sensor=%s code=%u voltage=%.6f valid=%u write=%u",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(code), s.voltage,
                s.valid ? 1u : 0u, writeOk ? 1u : 0u);
        if (s.valid) { baselineSum += s.voltage; ++baseCount; }
    }
    if (baseCount == 0) {
        r.errorCode = 2;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=baseline error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
        return r;
    }
    r.baselineV = baselineSum / static_cast<float>(baseCount);
    emitLog(logFn, "NULLING_BASELINE_DONE ch=%u sensor=%s baseline=%.6f validSamples=%u",
            static_cast<unsigned>(ch), sensorName(ch), r.baselineV,
            static_cast<unsigned>(baseCount));

    emitStageTransition(logFn, ch, "baseline", "exponential");
    pauseForMonitor(tickFn);

    uint16_t low = 0, high = 0;
    if (!findRange(ads, dac, ch, r.baselineV, low, high, logFn, tickFn, config)) {
        r.errorCode = 3;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=exponential error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
        return r;
    }

    emitStageTransition(logFn, ch, "exponential", "binary");
    pauseForMonitor(tickFn);

    uint16_t selected = binarySearch(ads, dac, ch, r.baselineV, low, high, logFn, tickFn, config);

    emitStageTransition(logFn, ch, "binary", "confirm");
    pauseForMonitor(tickFn);

    if (!confirmCode(ads, dac, ch, r.baselineV, selected, logFn, tickFn, config)) {
        r.errorCode = 4;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=confirm error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
        return r;
    }

    if (!dac.writeDac(ch, selected)) {
        r.errorCode = 5;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=final_write error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
        return r;
    }
    settle(tickFn);
    Snapshot after = readAverage(ads, ch, AVG_COUNT, tickFn);
    r.afterV = after.voltage;
    if (!after.valid) {
        r.errorCode = 6;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=after_read error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
        return r;
    }

    // Right at the zero crossing, noise can flip a verified-positive read
    // back negative on this independent final read. Priority is that the
    // final result must be positive: keep nudging the DAC code up one LSB at
    // a time and re-checking, instead of failing the whole channel outright.
    uint8_t finalBumps = 0;
    while (after.voltage < config.minFinalV &&
           finalBumps < FINAL_CHECK_MAX_BUMPS &&
           selected < board::GLD_DAC_CODE_MAX) {
        ++selected;
        ++finalBumps;
        emitLog(logFn, "NULLING_FINAL_BUMP ch=%u sensor=%s code=%u previousVoltage=%.9f bump=%u",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(selected), after.voltage,
                static_cast<unsigned>(finalBumps));
        if (!dac.writeDac(ch, selected)) {
            r.errorCode = 5;
            emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=final_write error=%u reason=%s",
                    static_cast<unsigned>(ch), sensorName(ch),
                    static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
            return r;
        }
        settle(tickFn);
        after = readAverage(ads, ch, AVG_COUNT, tickFn);
        r.afterV = after.voltage;
        if (!after.valid) {
            r.errorCode = 6;
            emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=after_read error=%u reason=%s",
                    static_cast<unsigned>(ch), sensorName(ch),
                    static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
            return r;
        }
    }

    if (after.voltage < config.minFinalV) {
        r.errorCode = 7;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=final_check error=%u reason=%s after=%.9f min=%.9f bumps=%u",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode),
                after.voltage, config.minFinalV, static_cast<unsigned>(finalBumps));
        return r;
    }

    r.dacCode  = selected;
    r.success  = true;
    r.errorCode = 0;
    emitLog(logFn, "NULLING_CH_OK ch=%u sensor=%s dac=%u baseline=%.6f after=%.9f",
            static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(r.dacCode), r.baselineV, r.afterV);
    return r;
}

}  // namespace

GldNullingServiceResult runNullingService(GldAds1256Reader& ads,
                                          GldDacMux& dac,
                                          GldNullingLogFn logFn,
                                          GldNullingTickFn tickFn,
                                          const GldNullingConfig& config) {
    GldNullingServiceResult out{};
    out.status = GldNullingStatus::Ok;

    emitLog(logFn, "NULLING_SERVICE_START channels=%u avgCount=%u confirmCount=%u settleMs=%lu thresholdV=%.6f minFinalV=%.6f",
            static_cast<unsigned>(board::SENSOR_COUNT),
            static_cast<unsigned>(AVG_COUNT),
            static_cast<unsigned>(CONFIRM_COUNT),
            static_cast<unsigned long>(SETTLE_MS),
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

    uint8_t successes = 0;
    for (uint8_t ch = 0; ch < board::SENSOR_COUNT; ++ch) {
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
    } else if (successes < board::SENSOR_COUNT) {
        out.status = GldNullingStatus::PartialSuccess;
    }
    emitLog(logFn, "NULLING_SERVICE_DONE status=%s successCount=%u/%u",
            gldNullingStatusName(out.status),
            static_cast<unsigned>(out.successCount),
            static_cast<unsigned>(board::SENSOR_COUNT));
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
    return read == sizeof(GldNullingConfig) && isNullingConfigValid(out);
}

const char* gldNullingStatusName(GldNullingStatus s) {
    switch (s) {
        case GldNullingStatus::Ok:               return "Ok";
        case GldNullingStatus::AdsNotReady:      return "AdsNotReady";
        case GldNullingStatus::DacNotReady:      return "DacNotReady";
        case GldNullingStatus::AllChannelsFailed:return "AllChannelsFailed";
        case GldNullingStatus::PartialSuccess:   return "PartialSuccess";
    }
    return "Unknown";
}

}  // namespace pgl::gld
