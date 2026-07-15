#pragma once

#include <cstdint>

#include <SPI.h>

class ADS1256;

namespace pgl::gld {

constexpr float GLD_ADS1256_VREF_VOLTS = 2.497f;
constexpr uint8_t GLD_ADS1256_DEFAULT_GAIN = 64;

enum class GldAds1256Status : uint8_t {
    Ok = 0,
    NotReady,
    DrdyTimeout,
    InvalidChannel,
};

struct GldAds1256Reading {
    GldAds1256Status status;
    int32_t raw;
    float voltage;
    uint8_t gain;
    bool saturated;
};

class GldAds1256Reader {
public:
    bool begin(SPIClass& spi);
    uint8_t readStatusRegister();
    uint8_t readMuxRegister();
    uint8_t readAdconRegister();
    uint8_t readDrateRegister();
    GldAds1256Reading readChannel(uint8_t channel);
    bool ready() const { return initialized_; }

private:
    SPIClass* spi_ = nullptr;
    ADS1256* ads_ = nullptr;
    bool initialized_ = false;
    uint8_t pgaIndex_[8]{};
    uint8_t gainConfirmDown_[8]{};
    uint8_t gainConfirmUp_[8]{};

    bool gainCalibrate(uint8_t channel);
    uint8_t getCurrentGain(uint8_t channel) const;
    void applyGain(uint8_t channel);
    float convertToVoltage(long raw, uint8_t pgaGain) const;
    bool readSingleInternal(uint8_t channel, long& raw);
};

const char* gldAds1256StatusName(GldAds1256Status status);

}  // namespace pgl::gld
