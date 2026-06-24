#pragma once

#include <cstdint>

#include <Wire.h>

namespace pgl::gld {

enum class GldDacMuxStatus : uint8_t {
    Ok = 0,
    NotReady,
    InvalidChannel,
    MuxSelectFailed,
    DacWriteFailed,
};

class GldDacMux {
public:
    bool begin(TwoWire& i2c = Wire);
    bool writeDac(uint8_t sensorChannel, uint16_t value);
    bool writeAll(uint16_t value);
    bool ready() const { return initialized_; }

private:
    TwoWire* i2c_ = nullptr;
    bool initialized_ = false;
    uint16_t lastValue_[8]{};

    bool selectMux(uint8_t muxChannel);
    bool writeRaw(uint16_t value);
};

const char* gldDacMuxStatusName(GldDacMuxStatus status);

}  // namespace pgl::gld
