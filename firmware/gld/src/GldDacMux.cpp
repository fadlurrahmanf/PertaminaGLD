#include "GldDacMux.h"

#include <Arduino.h>
#include <TCA9548.h>

#include "BoardPins.h"

namespace pgl::gld {

namespace {

TCA9548* mux = nullptr;
constexpr uint8_t MCP4725_DAC_REGISTER = 0x40;
constexpr uint16_t DAC_I2C_TIMEOUT_MS = 50;

}  // namespace

bool GldDacMux::begin(TwoWire& i2c) {
    i2c_ = &i2c;
    i2c_->begin(board::PIN_I2C_SDA, board::PIN_I2C_SCL);
#if defined(ARDUINO_ARCH_ESP32)
    i2c_->setTimeOut(DAC_I2C_TIMEOUT_MS);
#endif

    if (mux == nullptr) {
        mux = new TCA9548(board::TCA9548A_ADDR, i2c_);
    }

    if (!mux->begin()) {
        initialized_ = false;
        return false;
    }

    initialized_ = true;
    return true;
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
    if (i2c_ == nullptr) {
        return false;
    }

    const uint8_t high = static_cast<uint8_t>(value >> 4);
    const uint8_t low = static_cast<uint8_t>((value & 0x0F) << 4);
    i2c_->beginTransmission(board::MCP4725_ADDR);
    i2c_->write(MCP4725_DAC_REGISTER);
    i2c_->write(high);
    i2c_->write(low);
    return i2c_->endTransmission() == 0;
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
