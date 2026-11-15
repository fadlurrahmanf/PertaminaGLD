// Real GldDacMux and GldNullingService against independent physical-map
// doubles. This is host-only; no physical behavior or gas accuracy is proven.
#include <cassert>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include "BoardPins.h"
#include "GldAds1256Reader.h"
#include "GldDacMux.h"
#include "GldPcf8574.h"
#include "GldNullingService.h"
#include "Preferences.h"
#include "TCA9548.h"

#if PGL_GLD_BOARD_PROFILE_GLD2
static const uint8_t physicalMux[8] = {7,6,5,4,3,2,1,0};
#else
static const uint8_t physicalMux[8] = {7,6,5,0,1,2,3,4};
#endif
static const uint8_t physicalEn[8] = {0,6,7,3,4,5,2,1};
static uint32_t fakeMillis = 0;
static uint16_t dacByPhysicalMux[8]{};
static uint8_t selectedMux = 0;
static uint8_t txAddress = 0;
static uint8_t txBytes[3]{};
static unsigned txLength = 0;
static int failMux = -1, badAdc = -1, saturatedAdc = -1;
static unsigned dacWrites[8]{}, adcReads[8]{};
static uint8_t physicalPower = 0xff;
static std::vector<unsigned char> saved;
static unsigned nvsWrites = 0;
static uint8_t nullingProfileId = 0;

uint32_t millis() { return fakeMillis; }
void delay(uint32_t ms) { fakeMillis += ms; }
void logPrintln(const char*) {}
void logPrintf(const char*, ...) {}
TwoWire Wire;
bool TwoWire::begin(int, int) { return true; }
void TwoWire::end() {}
void TwoWire::setTimeOut(uint16_t) {}
void TwoWire::beginTransmission(uint8_t address) { txAddress = address; txLength = 0; }
void TwoWire::write(uint8_t value) { if (txLength < 3) txBytes[txLength++] = value; }
uint8_t TwoWire::endTransmission() {
    if (txAddress != 0x60 || txLength != 3) return 0;
    if (selectedMux == failMux) return 1;
    dacByPhysicalMux[selectedMux] = static_cast<uint16_t>((txBytes[1] << 4) | (txBytes[2] >> 4));
    ++dacWrites[selectedMux];
    return 0;
}
size_t TwoWire::requestFrom(uint8_t, uint8_t) { return 0; }
int TwoWire::available() { return 0; }
int TwoWire::read() { return -1; }
bool TCA9548::selectChannel(uint8_t channel) { selectedMux = channel; return true; }
bool Preferences::begin(const char*, bool) { return true; }
void Preferences::end() {}
size_t Preferences::putBytes(const char*, const void* data, size_t size) {
    ++nvsWrites;
    const auto* p = static_cast<const unsigned char*>(data);
    saved.assign(p, p + size);
    return size;
}
size_t Preferences::getBytes(const char*, void* data, size_t size) {
    if (saved.size() != size) return 0;
    std::memcpy(data, saved.data(), size);
    return size;
}

#include "adc_gate.inc"
namespace pgl::gld {
GldPcf8574::~GldPcf8574() {}
bool GldPcf8574::begin(TwoWire& i2c) { i2c_ = &i2c; ready_ = true; outputs_ = 0xff; return true; }
bool GldPcf8574::writeOutputs(uint8_t value) { outputs_ = physicalPower = value; return true; }
bool GldAds1256Reader::begin(SPIClass&) { initialized_ = true; return true; }
GldAds1256Reading GldAds1256Reader::readChannel(uint8_t channel) {
    ++fakeMillis;
    const uint8_t ain = adsInputForSensor(channel);
    assert(ain < 8);
    ++adcReads[ain];
    const bool powerOk = !board::HAS_PCF8574 || (physicalPower & (1u << physicalEn[ain]));
    const bool bad = ain == badAdc || !powerOk;
    // Sensor AIN channel is wired to this literal physical TCA branch. A bad
    // firmware mux map therefore no longer changes that channel's voltage.
    const float voltage = 0.010f + 0.0001f * dacByPhysicalMux[physicalMux[ain]];
    return {bad ? GldAds1256Status::NotReady : GldAds1256Status::Ok,
            0, voltage, 64, ain == saturatedAdc};
}
}  // namespace pgl::gld

#include "GldDacMux.cpp"
#include "GldNullingService.cpp"
#include "save_gate.inc"

static void resetFixture() {
    std::memset(dacByPhysicalMux, 0, sizeof(dacByPhysicalMux));
    std::memset(dacWrites, 0, sizeof(dacWrites));
    std::memset(adcReads, 0, sizeof(adcReads));
    fakeMillis = 0; selectedMux = 0; failMux = badAdc = saturatedAdc = -1;
}

int main() {
    using namespace pgl::gld;
    GldPcf8574 pcf;
    assert(pcf.begin(Wire));
    GldDacMux dac;
    dac.setRestoreSensorPowerAfterWrite(false);
    assert(dac.begin(Wire, &pcf));
    SPIClass spi;
    GldAds1256Reader ads;
    assert(ads.begin(spi));
    GldNullingConfig config{};
    config.thresholdV = 0.001f;

    resetFixture();
    const auto good = runNullingService(ads, dac, nullptr, nullptr, config);
    assert(good.status == GldNullingStatus::Ok && good.successCount == 8);
    for (unsigned ch = 0; ch < 8; ++ch) {
        assert(good.profile.channelOk[ch] && adcReads[ch] && dacWrites[physicalMux[ch]]);
        assert(good.profile.dacCode[ch] == dacByPhysicalMux[physicalMux[ch]]);
    }
    GldNullingProfile committed{};
    assert(saveCompleteNullingProfile(good, committed));
    assert(nvsWrites == 1 && isNullingProfileValid(committed));
    const auto before = saved;

    resetFixture();
    badAdc = 3;
    const auto partial = runNullingService(ads, dac, nullptr, nullptr, config);
    assert(partial.status == GldNullingStatus::PartialSuccess && partial.successCount == 7);
    assert(!partial.profile.channelOk[3]);
    GldNullingProfile ignored{};
    assert(!saveCompleteNullingProfile(partial, ignored));
    assert(nvsWrites == 1 && saved == before);

    resetFixture();
    saturatedAdc = 4;
    const auto saturated = runNullingService(ads, dac, nullptr, nullptr, config);
    assert(saturated.status == GldNullingStatus::PartialSuccess && saturated.successCount == 7);
    assert(!saveCompleteNullingProfile(saturated, ignored));
    assert(nvsWrites == 1 && saved == before);

    resetFixture();
    failMux = physicalMux[5];
    const auto i2cFail = runNullingService(ads, dac, nullptr, nullptr, config);
    assert(i2cFail.status == GldNullingStatus::PartialSuccess && i2cFail.successCount == 7);
    assert(!saveCompleteNullingProfile(i2cFail, ignored));
    assert(nvsWrites == 1 && saved == before);

    // Reproduce the primitive behind the single-channel handler risk: the
    // scan changes the selected DAC before it knows whether ADC is healthy.
    // This deliberately tests the service only, not the serial handler or a
    // real board. The caller must restore/invalidate after such a failure.
    resetFixture();
    for (uint8_t ch = 0; ch < 8; ++ch) assert(dac.writeDac(ch, committed.dacCode[ch]));
    assert(committed.dacCode[3] != 0);
    badAdc = 3;
    const auto singleFail = runNullingServiceSingleChannel(ads, dac, 3, nullptr, nullptr, config);
    assert(!singleFail.success);
    assert(dacByPhysicalMux[physicalMux[3]] != committed.dacCode[3]);
    assert(nvsWrites == 1 && saved == before);
    std::puts(PGL_GLD_BOARD_PROFILE_GLD_ATEX ? "ATEX native nulling PASS" :
              PGL_GLD_BOARD_PROFILE_GLD2 ? "GLD2 native nulling PASS" : "GLD1 native nulling PASS");
}

