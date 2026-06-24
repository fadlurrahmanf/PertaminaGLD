#include "GldNullingService.h"

#include <Arduino.h>
#include <Preferences.h>

#include <cmath>
#include <cstdint>

#include "BoardPins.h"

namespace pgl::gld {

namespace {

constexpr uint8_t  AVG_COUNT            = 8;
constexpr uint8_t  CONFIRM_COUNT        = 5;
constexpr uint16_t BASELINE_PRESCAN_MAX = 10;
constexpr uint16_t EXP_INIT_STEP        = 1;
constexpr uint16_t EXP_MAX_STEP         = 2048;
constexpr uint8_t  CONFIRM_WINDOW       = 10;
constexpr uint32_t SETTLE_MS            = 5;
constexpr float    THRESHOLD_V          = 0.0001f;

constexpr const char* NVS_NAMESPACE = "gld-null";
constexpr const char* NVS_KEY       = "profile";

struct Snapshot {
    float   voltage;
    bool    valid;
};

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
               uint16_t& outLow, uint16_t& outHigh) {
    uint16_t step     = EXP_INIT_STEP;
    uint16_t previous = 0;
    uint16_t current  = 1;

    while (current <= board::GLD_DAC_CODE_MAX) {
        if (!dac.writeDac(ch, current)) return false;
        delay(SETTLE_MS);
        const Snapshot snap = readAverage(ads, ch, AVG_COUNT);
        if (snap.valid && fabsf(snap.voltage - baselineV) >= THRESHOLD_V) {
            outLow  = previous;
            outHigh = current;
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
    return false;
}

uint16_t binarySearch(GldAds1256Reader& ads, GldDacMux& dac,
                      uint8_t ch, float baselineV,
                      uint16_t low, uint16_t high) {
    while (low + 1 < high) {
        const uint16_t mid = static_cast<uint16_t>((low + high) / 2);
        dac.writeDac(ch, mid);
        delay(SETTLE_MS);
        const Snapshot snap = readAverage(ads, ch, AVG_COUNT);
        if (fabsf(snap.voltage - baselineV) < THRESHOLD_V) {
            low = mid;
        } else {
            high = mid;
        }
    }
    return high;
}

bool confirmCode(GldAds1256Reader& ads, GldDacMux& dac,
                 uint8_t ch, float baselineV, uint16_t& dacCode) {
    int start = static_cast<int>(dacCode) - 5;
    if (start < board::GLD_DAC_CODE_MIN) start = board::GLD_DAC_CODE_MIN;
    int end = start + static_cast<int>(CONFIRM_WINDOW) - 1;
    if (end > board::GLD_DAC_CODE_MAX) {
        end   = board::GLD_DAC_CODE_MAX;
        start = max<int>(board::GLD_DAC_CODE_MIN,
                         end - static_cast<int>(CONFIRM_WINDOW) + 1);
    }
    for (int code = start; code <= end; ++code) {
        dac.writeDac(ch, static_cast<uint16_t>(code));
        delay(SETTLE_MS);
        const Snapshot snap = readAverage(ads, ch, CONFIRM_COUNT);
        if (snap.valid && fabsf(snap.voltage - baselineV) >= THRESHOLD_V) {
            dacCode = static_cast<uint16_t>(code);
            return true;
        }
    }
    return false;
}

struct ChannelResult {
    uint16_t dacCode;
    float    baselineV;
    float    afterV;
    bool     success;
    uint8_t  errorCode;
};

ChannelResult nullOneChannel(GldAds1256Reader& ads, GldDacMux& dac, uint8_t ch) {
    ChannelResult r{};
    r.success = false;

    if (!dac.writeDac(ch, 0)) { r.errorCode = 1; return r; }
    delay(SETTLE_MS);

    // Baseline prescan at low DAC codes
    float baselineSum  = 0.0f;
    uint8_t baseCount  = 0;
    for (uint16_t code = 0; code <= BASELINE_PRESCAN_MAX; ++code) {
        dac.writeDac(ch, code);
        delay(SETTLE_MS);
        const Snapshot s = readAverage(ads, ch, AVG_COUNT);
        if (s.valid) { baselineSum += s.voltage; ++baseCount; }
    }
    if (baseCount == 0) { r.errorCode = 2; return r; }
    r.baselineV = baselineSum / static_cast<float>(baseCount);

    uint16_t low = 0, high = 0;
    if (!findRange(ads, dac, ch, r.baselineV, low, high)) {
        r.errorCode = 3;
        return r;
    }

    uint16_t selected = binarySearch(ads, dac, ch, r.baselineV, low, high);
    if (!confirmCode(ads, dac, ch, r.baselineV, selected)) {
        r.errorCode = 4;
        return r;
    }

    if (!dac.writeDac(ch, selected)) { r.errorCode = 5; return r; }
    delay(SETTLE_MS);
    const Snapshot after = readAverage(ads, ch, AVG_COUNT);
    if (!after.valid) { r.errorCode = 6; return r; }

    r.dacCode  = selected;
    r.afterV   = after.voltage;
    r.success  = true;
    r.errorCode = 0;
    return r;
}

}  // namespace

GldNullingServiceResult runNullingService(GldAds1256Reader& ads, GldDacMux& dac) {
    GldNullingServiceResult out{};
    out.status = GldNullingStatus::Ok;

    if (!ads.ready()) { out.status = GldNullingStatus::AdsNotReady; return out; }
    if (!dac.ready()) { out.status = GldNullingStatus::DacNotReady; return out; }

    uint8_t successes = 0;
    for (uint8_t ch = 0; ch < board::SENSOR_COUNT; ++ch) {
        const ChannelResult cr = nullOneChannel(ads, dac, ch);
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
