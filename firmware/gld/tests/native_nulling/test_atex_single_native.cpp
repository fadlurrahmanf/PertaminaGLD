// Production onRunNullingSingleJson compiled verbatim with fake dependencies.
// Tests handler behavior, not hardware, ADC timing, or I2C electrical effects.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

struct FakeJsonValue {
    int value;
    template<class T> T as() const { return static_cast<T>(value); }
};
template<unsigned N> struct StaticJsonDocument {
    bool present = false;
    int channel = 0;
    bool containsKey(const char*) const { return present; }
    FakeJsonValue operator[](const char*) const { return {channel}; }
};
template<unsigned N> bool deserializeJson(StaticJsonDocument<N>& doc, const char* payload) {
    if (!std::strcmp(payload, "invalid")) return true;
    doc.present = std::strcmp(payload, "missing") != 0;
    doc.channel = std::atoi(payload);
    return false;
}
struct FakeAds {} ads;
struct FakeDac {
    int value = 0;
    unsigned writes = 0, failWriteBits = 0;
    bool writeDac(uint8_t, uint16_t code) {
        ++writes;
        if (failWriteBits & (1u << writes)) return false;
        value = code;
        return true;
    }
} dac;
bool nullingProfileApplied = true, lastInferenceValid = true, modelProfileReady = true;
bool dacReady = true;
bool runtimeMcpReadbackVerified[8] = {true,true,true,true,true,true,true,true};
uint8_t nullingProfileId = 4;
int ensureCalls = 0, serviceCalls = 0, saveCalls = 0;
bool hardwareReady = true, haveProfile = true, scanSuccess = true, saveSuccess = true;
bool corruptOnSaveFailure = false;
uint16_t scanCode = 321;
const char* ackState = nullptr;
const char* ackDetail = nullptr;

namespace pgl { namespace gld {
namespace board { constexpr uint8_t SENSOR_COUNT = 8; }
struct GldNullingProfile {
    uint8_t profileId = 4;
    bool valid = true;
    uint16_t dacCode[8] = {123,123,123,123,123,123,123,123};
    float baselineV[8] = {}, afterV[8] = {};
    uint8_t channelOk[8] = {1,1,1,1,1,1,1,1};
};
struct GldNullingSingleResult {
    bool success = false;
    uint16_t dacCode = 0;
    float baselineV = 0, afterV = 0;
};
struct GldNullingConfig {} nullingConfig;
GldNullingProfile saved;
bool isNullingProfileValid(const GldNullingProfile& p) {
    if (!p.valid || !p.profileId) return false;
    for (int ch = 0; ch < 8; ++ch) if (!p.channelOk[ch] || p.dacCode[ch] > 4095) return false;
    return true;
}
bool loadNullingProfile(GldNullingProfile& out) { out = saved; return haveProfile; }
bool saveNullingProfile(const GldNullingProfile& input) {
    ++saveCalls;
    if (!saveSuccess) {
        if (corruptOnSaveFailure) saved.valid = false;
        return false;
    }
    saved = input;
    return true;
}
GldNullingSingleResult runNullingServiceSingleChannel(FakeAds&, FakeDac&, uint8_t,
                                                       void(*)(const char*), void(*)(), GldNullingConfig&) {
    ++serviceCalls;
    dac.value = 777;  // the real service writes its search values before returning
    GldNullingSingleResult r;
    r.success = scanSuccess; r.dacCode = scanCode; r.baselineV = 0.01f; r.afterV = 0.02f;
    return r;
}
} }
using pgl::gld::nullingConfig;
bool ensureNullingHardwareReady() { ++ensureCalls; return hardwareReady; }
void nullingLogLine(const char*) {}
void firmwareServiceTick() {}
void logPrintf(const char*, ...) {}
void emitCommandAck(const char*, const char* state, const char* detail, bool) {
    ackState = state; ackDetail = detail;
}

#include "handler.inc"

static void reset() {
    dac = FakeDac{};
    dac.value = 123;
    nullingProfileApplied = lastInferenceValid = modelProfileReady = dacReady = true;
    for (bool& verified : runtimeMcpReadbackVerified) verified = true;
    nullingProfileId = 4;
    ensureCalls = serviceCalls = saveCalls = 0;
    hardwareReady = haveProfile = scanSuccess = saveSuccess = true;
    corruptOnSaveFailure = false;
    scanCode = 321;
    ackState = ackDetail = nullptr;
    pgl::gld::saved = pgl::gld::GldNullingProfile{};
}

#if PGL_GLD_BOARD_PROFILE_GLD_ATEX
static void assertInvalidated() {
    assert(!nullingProfileApplied && !lastInferenceValid && !modelProfileReady);
    assert(!runtimeMcpReadbackVerified[3]);
}
#endif

int main() {
    reset(); onRunNullingSingleJson("invalid");
    assert(!std::strcmp(ackState, "error") && !serviceCalls && !dac.writes);
    reset(); onRunNullingSingleJson("missing");
    assert(!std::strcmp(ackState, "rejected") && !serviceCalls && !dac.writes);
    reset(); onRunNullingSingleJson("9");
    assert(!std::strcmp(ackState, "rejected") && !serviceCalls && !dac.writes);

#if PGL_GLD_BOARD_PROFILE_GLD_ATEX
    reset(); haveProfile = false; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "rejected") && !ensureCalls && !serviceCalls && !dac.writes);
    reset(); pgl::gld::saved.valid = false; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "rejected") && !ensureCalls && !serviceCalls && !dac.writes);
    reset(); pgl::gld::saved.profileId = UINT8_MAX; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "rejected") && !ensureCalls && !serviceCalls && !dac.writes);
    reset(); hardwareReady = false; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "error") && ensureCalls == 1 && !serviceCalls && !dac.writes);
    assert(nullingProfileApplied && lastInferenceValid);

    reset(); scanSuccess = false; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "failed") && serviceCalls == 1 && dac.writes == 1 && dac.value == 123);
    assert(!saveCalls && dacReady); assertInvalidated();
    reset(); scanSuccess = false; dac.failWriteBits = 1u << 1; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "failed") && dac.value == 777 && !dacReady); assertInvalidated();

    reset(); scanCode = 5000; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "error") && dac.writes == 1 && dac.value == 123 && !saveCalls);
    assertInvalidated();
    reset(); scanCode = 5000; dac.failWriteBits = 1u << 1; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "error") && !dacReady && !saveCalls); assertInvalidated();
    reset(); dac.failWriteBits = 1u << 1; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "error") && dac.writes == 2 && dac.value == 123 && !saveCalls);
    assert(dacReady); assertInvalidated();
    reset(); dac.failWriteBits = (1u << 1) | (1u << 2); onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "error") && dac.writes == 2 && !dacReady); assertInvalidated();

    reset(); saveSuccess = false; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "error") && saveCalls == 1 && dac.writes == 2 && dac.value == 123);
    assert(pgl::gld::saved.profileId == 4 && dacReady); assertInvalidated();
    reset(); saveSuccess = false; corruptOnSaveFailure = true; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "error") && saveCalls == 1 && dac.value == 123);
    assert(!pgl::gld::isNullingProfileValid(pgl::gld::saved)); assertInvalidated();
    reset(); saveSuccess = false; dac.failWriteBits = 1u << 2; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "error") && saveCalls == 1 && !dacReady); assertInvalidated();

    reset(); onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "ok") && saveCalls == 1 && dac.value == 321);
    assert(nullingProfileId == 5 && pgl::gld::saved.profileId == 5 && pgl::gld::saved.dacCode[3] == 321);
    assert(std::strstr(ackDetail, "restart") != nullptr); assertInvalidated();
    std::puts("ATEX single-null handler: all fail-closed cases PASS");
#else
    // Existing profile behavior stays byte-for-byte in the #else branch.
    reset(); haveProfile = false; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "rejected"));
#if PGL_GLD_BOARD_PROFILE_GLD2
    assert(serviceCalls == 1);  // baseline GLD2 checks the profile after scan
    reset(); scanSuccess = false; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "failed") && dac.value == 777 && !dac.writes);
    assert(nullingProfileApplied && lastInferenceValid);
    std::puts("GLD2 protected single-null baseline PASS");
#else
    assert(serviceCalls == 0);  // existing GLD1 checks the profile first
    reset(); scanSuccess = false; onRunNullingSingleJson("3");
    assert(!std::strcmp(ackState, "failed") && dac.value == 123 && dac.writes == 1);
    assert(!nullingProfileApplied && !lastInferenceValid);
    std::puts("GLD1 protected single-null baseline PASS");
#endif
#endif
}
