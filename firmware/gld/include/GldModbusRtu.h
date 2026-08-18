#pragma once

#include <Arduino.h>

#include <cstddef>
#include <cstdint>

namespace pgl::gld {

// GLD2 Modbus RTU input-register contract (all values are unsigned 16-bit):
// 0=status bitfield, 1=gas class, 2=confidence percent, 3=battery mV,
// 4=ST_P source (1=24 V, 0=battery), 5=external-power flag,
// 6=LoRa TX counter low word, 7=GLD node ID.
struct GldModbusRtuSnapshot {
    uint16_t statusBits = 0;
    uint16_t gasClass = 0;
    uint16_t confidence = 0;
    uint16_t batteryMv = 0;
    uint16_t source24V = 0;
    uint16_t externalPower = 0;
    uint16_t txCounterLow = 0;
    uint16_t nodeId = 0;
};

class GldModbusRtu {
public:
    static constexpr uint8_t kDefaultUnitId = 1;
    static constexpr uint32_t kDefaultBaud = 9600;

    bool begin(uint8_t unitId, uint32_t baud, int dirPin, int rxPin, int txPin);
    void poll(const GldModbusRtuSnapshot& snapshot);
    bool ready() const { return ready_; }

private:
    static constexpr size_t kMaxFrameBytes = 64;
    static constexpr uint8_t kRegisterCount = 8;

    uint16_t crc16(const uint8_t* data, size_t length) const;
    void handleFrame(const GldModbusRtuSnapshot& snapshot);
    void sendException(uint8_t function, uint8_t exceptionCode);
    void sendRegisters(uint8_t function, uint16_t firstRegister,
                       uint16_t registerCount,
                       const GldModbusRtuSnapshot& snapshot);
    void beginTransmit();
    void endTransmit();

    HardwareSerial serial_{1};
    uint8_t unitId_ = kDefaultUnitId;
    int dirPin_ = -1;
    uint8_t rxBuffer_[kMaxFrameBytes]{};
    size_t rxLength_ = 0;
    uint32_t lastRxByteMs_ = 0;
    bool ready_ = false;
};

}  // namespace pgl::gld
