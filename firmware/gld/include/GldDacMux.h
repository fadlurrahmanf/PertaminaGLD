#pragma once

#include <cstdint>

#include <Wire.h>

namespace pgl::gld {

class GldPcf8574;

enum class GldDacMuxStatus : uint8_t {
    Ok = 0,
    NotReady,
    InvalidChannel,
    MuxSelectFailed,
    DacWriteFailed,
};

class GldDacMux {
public:
    bool begin(TwoWire& i2c = Wire, GldPcf8574* sensorPower = nullptr);
    bool writeDac(uint8_t sensorChannel, uint16_t value);
    // Writes both the volatile DAC register and its EEPROM shadow. Use only
    // when a saved nulling code differs, never for normal runtime control.
    bool writeDacPersistent(uint8_t sensorChannel, uint16_t value);
    // Reads the volatile DAC register from the MCP4725 selected by this
    // sensor channel.  This is hardware readback, not the local lastValue
    // cache maintained after a successful write transaction.
    bool readDac(uint8_t sensorChannel, uint16_t& value);
    bool writeAll(uint16_t value);
    bool restoreSensorPower();
    void setSensorPowerSettleMs(uint16_t value) { sensorPowerSettleMs_ = value; }
    void setRestoreSensorPowerAfterWrite(bool enabled) { restoreSensorPowerAfterWrite_ = enabled; }
    // Capture the current PCF8574 mask as the eventual restore point before a
    // scoped diagnostic/nulling isolation session.
    void captureSensorPowerState();
    // Battery sessions may isolate one TPS22919 branch at a time.  On
    // external power, normal operation preserves the operator's PCF8574 mask.
    void setAutomaticSensorPowerControl(bool enabled) { automaticSensorPowerControl_ = enabled; }
    bool ready() const { return initialized_; }
    uint16_t lastValue(uint8_t sensorChannel) const;

private:
    TwoWire* i2c_ = nullptr;
    GldPcf8574* sensorPower_ = nullptr;
    bool initialized_ = false;
    int8_t poweredSensorChannel_ = -1;
    uint8_t powerOutputsBeforeBegin_ = 0;
    bool powerOutputsCaptured_ = false;
    uint16_t sensorPowerSettleMs_ = 50;
    bool restoreSensorPowerAfterWrite_ = true;
    bool automaticSensorPowerControl_ = true;
    uint16_t lastValue_[8]{};

    bool selectMux(uint8_t muxChannel);
    bool selectSensorPower(uint8_t sensorChannel);
    bool writeRaw(uint16_t value);
    bool writeRawPersistent(uint16_t value);
    bool readRaw(uint16_t& value);
};

const char* gldDacMuxStatusName(GldDacMuxStatus status);

}  // namespace pgl::gld
