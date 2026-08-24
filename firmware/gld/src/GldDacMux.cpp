#include "GldDacMux.h"

#include <Arduino.h>
#include <TCA9548.h>

#include "BoardPins.h"
#include "GldPcf8574.h"

namespace pgl::gld {

namespace {

TCA9548* mux = nullptr;
constexpr uint8_t MCP4725_DAC_REGISTER = 0x40;
constexpr uint16_t DAC_I2C_TIMEOUT_MS = 50;
constexpr uint8_t DAC_WRITE_ATTEMPTS = 3;

void recoverTcaRootBus(TwoWire& i2c) {
    // A failed downstream MCP transaction must not leave the next sensor
    // stranded behind a stale TCA channel. Reinitialise the ESP I2C peripheral
    // and explicitly disable every TCA branch before the retry.
    i2c.end();
    delay(2);
    i2c.begin(board::PIN_I2C_SDA, board::PIN_I2C_SCL);
#if defined(ARDUINO_ARCH_ESP32)
    i2c.setTimeOut(DAC_I2C_TIMEOUT_MS);
#endif
    i2c.beginTransmission(board::TCA9548A_ADDR);
    i2c.write(static_cast<uint8_t>(0x00));
    (void)i2c.endTransmission();
    delay(5);
    if (mux != nullptr) mux->setForced(true);
}

}  // namespace

bool GldDacMux::begin(TwoWire& i2c, GldPcf8574* sensorPower) {
    i2c_ = &i2c;
    sensorPower_ = sensorPower;
    i2c_->begin(board::PIN_I2C_SDA, board::PIN_I2C_SCL);
#if defined(ARDUINO_ARCH_ESP32)
    i2c_->setTimeOut(DAC_I2C_TIMEOUT_MS);
#endif

    if (mux == nullptr) {
        mux = new TCA9548(board::TCA9548A_ADDR, i2c_);
    }

    // In battery sessions, downstream modules share MCP4725 address 0x60, so
    // isolate the required TPS22919 branch.  External-power operation keeps
    // the operator-selected PCF8574 state untouched.
    poweredSensorChannel_ = -1;
    powerOutputsCaptured_ = sensorPower_ != nullptr;
    if (powerOutputsCaptured_) powerOutputsBeforeBegin_ = sensorPower_->outputs();
    if (automaticSensorPowerControl_ && board::HAS_PCF8574 &&
        (sensorPower_ == nullptr ||
         !sensorPower_->writeOutputs(board::PCF8574_ALL_LOAD_SWITCHES_OFF))) {
        initialized_ = false;
        return false;
    }
    if (automaticSensorPowerControl_ && board::HAS_PCF8574) delay(sensorPowerSettleMs_);

    // The boot scanner also writes the TCA selection register directly.
    // Force this library instance to write its own mask rather than trusting
    // a stale cached mask from an earlier diagnostic or retry.
    mux->setForced(true);
    if (!mux->begin()) {
        (void)restoreSensorPower();
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

    if (!selectSensorPower(sensorChannel)) {
        return false;
    }

    const uint8_t muxChannel = static_cast<uint8_t>(board::SENSOR_TO_MUX_CH[sensorChannel]);
    bool writeOk = false;
    for (uint8_t attempt = 0; attempt < DAC_WRITE_ATTEMPTS && !writeOk; ++attempt) {
        if (attempt > 0 && i2c_ != nullptr) {
            recoverTcaRootBus(*i2c_);
        }
        writeOk = selectMux(muxChannel) && writeRaw(value);
    }
    const bool restoreOk = !restoreSensorPowerAfterWrite_ || restoreSensorPower();
    if (!writeOk || !restoreOk) return false;

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

bool GldDacMux::readDac(uint8_t sensorChannel, uint16_t& value) {
    value = 0;
    if (!initialized_ || sensorChannel >= board::SENSOR_COUNT) {
        return false;
    }
    if (!selectSensorPower(sensorChannel)) {
        return false;
    }

    const uint8_t muxChannel = static_cast<uint8_t>(board::SENSOR_TO_MUX_CH[sensorChannel]);
    bool readOk = false;
    for (uint8_t attempt = 0; attempt < DAC_WRITE_ATTEMPTS && !readOk; ++attempt) {
        if (attempt > 0 && i2c_ != nullptr) {
            recoverTcaRootBus(*i2c_);
        }
        readOk = selectMux(muxChannel) && readRaw(value);
    }
    const bool restoreOk = !restoreSensorPowerAfterWrite_ || restoreSensorPower();
    return readOk && restoreOk;
}

uint16_t GldDacMux::lastValue(uint8_t sensorChannel) const {
    return sensorChannel < board::SENSOR_COUNT ? lastValue_[sensorChannel] : 0;
}

void GldDacMux::captureSensorPowerState() {
    if (sensorPower_ == nullptr) return;
    powerOutputsBeforeBegin_ = sensorPower_->outputs();
    powerOutputsCaptured_ = true;
    poweredSensorChannel_ = -1;
}

bool GldDacMux::restoreSensorPower() {
    if (!automaticSensorPowerControl_) return true;
    if (!board::HAS_PCF8574 || sensorPower_ == nullptr || !powerOutputsCaptured_) return true;
    const bool restored = sensorPower_->writeOutputs(powerOutputsBeforeBegin_);
    if (restored) poweredSensorChannel_ = -1;
    return restored;
}

bool GldDacMux::selectMux(uint8_t muxChannel) {
    return mux != nullptr && mux->selectChannel(muxChannel);
}

bool GldDacMux::selectSensorPower(uint8_t sensorChannel) {
    if (!automaticSensorPowerControl_) return true;
    if (!board::HAS_PCF8574) return true;
    if (poweredSensorChannel_ == static_cast<int8_t>(sensorChannel)) return true;

    const uint8_t en = board::SENSOR_TO_POWER_EN[sensorChannel];
    const uint8_t outputs = static_cast<uint8_t>(1U << en);
    if (sensorPower_ == nullptr) return false;
    const bool wrote = sensorPower_->writeOutputs(outputs);
    if (!wrote) return false;
    delay(sensorPowerSettleMs_);
    poweredSensorChannel_ = static_cast<int8_t>(sensorChannel);
    return true;
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

bool GldDacMux::readRaw(uint16_t& value) {
    if (i2c_ == nullptr) {
        return false;
    }

    // MCP4725 Read Command returns five data bytes.  The volatile DAC register
    // code is bytes 2-3 (D11..D4, then D3..D0 in the high nibble); EEPROM data
    // follows afterwards.  Reading is intentionally done only after selecting
    // this channel's TCA branch because every MCP uses address 0x60.
    constexpr uint8_t MCP4725_READ_BYTES = 5;
    const size_t received = i2c_->requestFrom(static_cast<uint8_t>(board::MCP4725_ADDR),
                                              MCP4725_READ_BYTES);
    uint8_t response[MCP4725_READ_BYTES]{};
    uint8_t count = 0;
    while (i2c_->available() && count < MCP4725_READ_BYTES) {
        response[count++] = static_cast<uint8_t>(i2c_->read());
    }
    while (i2c_->available()) {
        (void)i2c_->read();
    }
    if (received != MCP4725_READ_BYTES || count != MCP4725_READ_BYTES) {
        return false;
    }
    value = static_cast<uint16_t>((static_cast<uint16_t>(response[1]) << 4) |
                                  (static_cast<uint16_t>(response[2]) >> 4));
    return true;
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
