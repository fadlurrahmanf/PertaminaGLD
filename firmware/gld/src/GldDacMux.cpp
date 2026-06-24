#include "GldDacMux.h"

#include <Arduino.h>
#include <MCP4725.h>
#include <TCA9548.h>

#include "BoardPins.h"

namespace pgl::gld {

namespace {

TCA9548* mux = nullptr;
MCP4725* dac = nullptr;

}  // namespace

bool GldDacMux::begin(TwoWire& i2c) {
    i2c_ = &i2c;
    i2c_->begin(board::PIN_I2C_SDA, board::PIN_I2C_SCL);

    if (mux == nullptr) {
        mux = new TCA9548(board::TCA9548A_ADDR, i2c_);
    }
    if (dac == nullptr) {
        dac = new MCP4725(board::MCP4725_ADDR, i2c_);
    }

    if (!mux->begin()) {
        initialized_ = false;
        return false;
    }

    initialized_ = true;
    return writeAll(1);
}

bool GldDacMux::writeDac(uint8_t sensorChannel, uint16_t value) {
    if (!initialized_ || sensorChannel >= board::SENSOR_COUNT || value > board::GLD_DAC_CODE_MAX) {
        return false;
    }

    const uint8_t muxChannel = static_cast<uint8_t>(board::SENSOR_TO_MUX_CH[sensorChannel]);
    if (!selectMux(muxChannel)) {
        return false;
    }
    if (!writeRaw(value)) {
        return false;
    }

    lastValue_[sensorChannel] = value;
    return true;
}

bool GldDacMux::writeAll(uint16_t value) {
    if (value > board::GLD_DAC_CODE_MAX) {
        return false;
    }

    for (uint8_t ch = 0; ch < board::SENSOR_COUNT; ++ch) {
        if (!writeDac(ch, value)) {
            return false;
        }
    }
    return true;
}

bool GldDacMux::selectMux(uint8_t muxChannel) {
    return mux != nullptr && mux->selectChannel(muxChannel);
}

bool GldDacMux::writeRaw(uint16_t value) {
    if (dac == nullptr) {
        return false;
    }

    // Always write through the selected mux channel. The MCP4725 library caches
    // values per object, but here one object is reused behind the mux.
    return dac->writeDAC(value, false) == MCP4725_OK;
}

const char* gldDacMuxStatusName(GldDacMuxStatus status) {
    switch (status) {
        case GldDacMuxStatus::Ok:
            return "Ok";
        case GldDacMuxStatus::NotReady:
            return "NotReady";
        case GldDacMuxStatus::InvalidChannel:
            return "InvalidChannel";
        case GldDacMuxStatus::MuxSelectFailed:
            return "MuxSelectFailed";
        case GldDacMuxStatus::DacWriteFailed:
            return "DacWriteFailed";
    }
    return "Unknown";
}

}  // namespace pgl::gld
