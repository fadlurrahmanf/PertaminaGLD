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
constexpr uint8_t  CONFIRM_WINDOW       = 10;
constexpr uint32_t SETTLE_MS            = 5;
constexpr float    THRESHOLD_V          = 0.0001f;
constexpr float    MIN_FINAL_V          = 0.0f;

constexpr const char* NVS_NAMESPACE = "gld-null";
constexpr const char* NVS_KEY       = "profile";

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

Snapshot readAverage(GldAds1256Reader& ads, uint8_t ch, uint8_t count) {
    float sum = 0.0f;
    bool valid = true;
    for (uint8_t i = 0; i < count; ++i) {
        const GldAds1256Reading r = ads.readChannel(ch);
        sum += r.voltage;
        valid = valid && (r.status == GldAds1256Status::Ok);
    }
    return {sum / static_cast<float>(count), valid};
}

bool findRange(GldAds1256Reader& ads, GldDacMux& dac,
               uint8_t ch, float baselineV,
               uint16_t& outLow, uint16_t& outHigh,
               GldNullingLogFn logFn) {
    uint16_t step     = EXP_INIT_STEP;
    uint16_t previous = 0;
    uint16_t current  = 1;
    emitLog(logFn, "NULLING_EXP_START ch=%u sensor=%s baseline=%.6f threshold=%.6f",
            static_cast<unsigned>(ch), sensorName(ch), baselineV, THRESHOLD_V);

    while (current <= board::GLD_DAC_CODE_MAX) {
        if (!dac.writeDac(ch, current)) {
            emitLog(logFn, "NULLING_EXP_WRITE_FAIL ch=%u sensor=%s code=%u",
                    static_cast<unsigned>(ch), sensorName(ch),
                    static_cast<unsigned>(current));
            return false;
        }
        delay(SETTLE_MS);
        const Snapshot snap = readAverage(ads, ch, AVG_COUNT);
        const float delta = fabsf(snap.voltage - baselineV);
        emitLog(logFn, "NULLING_EXP_STEP ch=%u sensor=%s code=%u voltage=%.6f delta=%.6f valid=%u",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(current), snap.voltage, delta,
                snap.valid ? 1u : 0u);
        if (snap.valid && delta >= THRESHOLD_V) {
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
                      GldNullingLogFn logFn) {
    emitLog(logFn, "NULLING_BIN_START ch=%u sensor=%s low=%u high=%u",
            static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(low), static_cast<unsigned>(high));
    while (low + 1 < high) {
        const uint16_t mid = static_cast<uint16_t>((low + high) / 2);
        const bool writeOk = dac.writeDac(ch, mid);
        delay(SETTLE_MS);
        const Snapshot snap = readAverage(ads, ch, AVG_COUNT);
        const float delta = fabsf(snap.voltage - baselineV);
        emitLog(logFn, "NULLING_BIN_STEP ch=%u sensor=%s low=%u high=%u mid=%u voltage=%.6f delta=%.6f valid=%u write=%u",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(low), static_cast<unsigned>(high),
                static_cast<unsigned>(mid), snap.voltage, delta,
                snap.valid ? 1u : 0u, writeOk ? 1u : 0u);
        if (delta < THRESHOLD_V) {
            low = mid;
        } else {
            high = mid;
        }
    }
    emitLog(logFn, "NULLING_BIN_DONE ch=%u sensor=%s selected=%u",
            static_cast<unsigned>(ch), sensorName(ch), static_cast<unsigned>(high));
    return high;
}

bool confirmCode(GldAds1256Reader& ads, GldDacMux& dac,
                 uint8_t ch, float baselineV, uint16_t& dacCode,
                 GldNullingLogFn logFn) {
    int start = static_cast<int>(dacCode) - 5;
    if (start < board::GLD_DAC_CODE_MIN) start = board::GLD_DAC_CODE_MIN;
    int end = start + static_cast<int>(CONFIRM_WINDOW) - 1;
    if (end > board::GLD_DAC_CODE_MAX) {
        end   = board::GLD_DAC_CODE_MAX;
        start = max<int>(board::GLD_DAC_CODE_MIN,
                         end - static_cast<int>(CONFIRM_WINDOW) + 1);
    }
    emitLog(logFn, "NULLING_CONFIRM_START ch=%u sensor=%s start=%d end=%d",
            static_cast<unsigned>(ch), sensorName(ch), start, end);
    for (int code = start; code <= end; ++code) {
        const bool writeOk = dac.writeDac(ch, static_cast<uint16_t>(code));
        delay(SETTLE_MS);
        const Snapshot snap = readAverage(ads, ch, CONFIRM_COUNT);
        const float delta = fabsf(snap.voltage - baselineV);
        const bool nonNegative = snap.voltage >= MIN_FINAL_V;
        emitLog(logFn, "NULLING_CONFIRM_STEP ch=%u sensor=%s code=%d voltage=%.9f delta=%.6f valid=%u positive=%u write=%u",
                static_cast<unsigned>(ch), sensorName(ch), code,
                snap.voltage, delta, snap.valid ? 1u : 0u,
                nonNegative ? 1u : 0u, writeOk ? 1u : 0u);
        if (writeOk && snap.valid && nonNegative && delta >= THRESHOLD_V) {
            dacCode = static_cast<uint16_t>(code);
            emitLog(logFn, "NULLING_CONFIRM_OK ch=%u sensor=%s code=%u",
                    static_cast<unsigned>(ch), sensorName(ch),
                    static_cast<unsigned>(dacCode));
            return true;
        }
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
                             uint8_t ch, GldNullingLogFn logFn) {
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
    delay(SETTLE_MS);

    emitLog(logFn, "NULLING_BASELINE_START ch=%u sensor=%s codeMin=%u codeMax=%u avgCount=%u",
            static_cast<unsigned>(ch), sensorName(ch),
            static_cast<unsigned>(board::GLD_DAC_CODE_MIN),
            static_cast<unsigned>(BASELINE_PRESCAN_MAX),
            static_cast<unsigned>(AVG_COUNT));
    float baselineSum  = 0.0f;
    uint8_t baseCount  = 0;
    for (uint16_t code = 0; code <= BASELINE_PRESCAN_MAX; ++code) {
        const bool writeOk = dac.writeDac(ch, code);
        delay(SETTLE_MS);
        const Snapshot s = readAverage(ads, ch, AVG_COUNT);
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

    uint16_t low = 0, high = 0;
    if (!findRange(ads, dac, ch, r.baselineV, low, high, logFn)) {
        r.errorCode = 3;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=exponential error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
        return r;
    }

    uint16_t selected = binarySearch(ads, dac, ch, r.baselineV, low, high, logFn);
    if (!confirmCode(ads, dac, ch, r.baselineV, selected, logFn)) {
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
    delay(SETTLE_MS);
    const Snapshot after = readAverage(ads, ch, AVG_COUNT);
    r.afterV = after.voltage;
    if (!after.valid) {
        r.errorCode = 6;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=after_read error=%u reason=%s",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode));
        return r;
    }
    if (after.voltage < MIN_FINAL_V) {
        r.errorCode = 7;
        emitLog(logFn, "NULLING_CH_FAIL ch=%u sensor=%s stage=final_check error=%u reason=%s after=%.9f min=%.9f",
                static_cast<unsigned>(ch), sensorName(ch),
                static_cast<unsigned>(r.errorCode), channelErrorName(r.errorCode),
                after.voltage, MIN_FINAL_V);
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
                                          GldNullingLogFn logFn) {
    GldNullingServiceResult out{};
    out.status = GldNullingStatus::Ok;

    emitLog(logFn, "NULLING_SERVICE_START channels=%u avgCount=%u confirmCount=%u settleMs=%lu",
            static_cast<unsigned>(board::SENSOR_COUNT),
            static_cast<unsigned>(AVG_COUNT),
            static_cast<unsigned>(CONFIRM_COUNT),
            static_cast<unsigned long>(SETTLE_MS));

    if (!ads.ready()) {
        out.status = GldNullingStatus::AdsNotReady;
        emitLog(logFn, "NULLING_SERVICE_BLOCKED status=%s", gldNullingStatusName(out.status));
        return out;
    }
    if (!dac.ready()) {
        out.status = GldNullingStatus::DacNotReady;
        emitLog(logFn, "NULLING_SERVICE_BLOCKED status=%s", gldNullingStatusName(out.status));
        return out;
    }

    uint8_t successes = 0;
    for (uint8_t ch = 0; ch < board::SENSOR_COUNT; ++ch) {
        const ChannelResult cr = nullOneChannel(ads, dac, ch, logFn);
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
