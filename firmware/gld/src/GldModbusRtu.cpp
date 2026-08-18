#include "GldModbusRtu.h"

namespace pgl::gld {
namespace {

constexpr uint32_t kRtuFrameGapMs = 4;  // > 3.5 character times at 9600 8N1.
constexpr uint8_t kFunctionReadHoldingRegisters = 0x03;
constexpr uint8_t kFunctionReadInputRegisters = 0x04;
constexpr uint8_t kExceptionIllegalFunction = 0x01;
constexpr uint8_t kExceptionIllegalAddress = 0x02;
constexpr uint8_t kExceptionIllegalValue = 0x03;

uint16_t readBe16(const uint8_t* data) {
    return static_cast<uint16_t>((static_cast<uint16_t>(data[0]) << 8) | data[1]);
}

void writeBe16(uint8_t* data, uint16_t value) {
    data[0] = static_cast<uint8_t>(value >> 8);
    data[1] = static_cast<uint8_t>(value & 0xFFU);
}

}  // namespace

bool GldModbusRtu::begin(uint8_t unitId, uint32_t baud, int dirPin, int rxPin, int txPin) {
    if (unitId == 0 || dirPin < 0 || rxPin < 0 || txPin < 0) return false;

    unitId_ = unitId;
    dirPin_ = dirPin;
    pinMode(static_cast<uint8_t>(dirPin_), OUTPUT);
    digitalWrite(static_cast<uint8_t>(dirPin_), LOW);  // THVD1410 receive mode.
    serial_.begin(baud, SERIAL_8N1, rxPin, txPin);
    ready_ = true;
    return true;
}

void GldModbusRtu::poll(const GldModbusRtuSnapshot& snapshot) {
    if (!ready_) return;

    while (serial_.available() > 0) {
        const int value = serial_.read();
        if (value < 0) break;
        if (rxLength_ < kMaxFrameBytes) {
            rxBuffer_[rxLength_++] = static_cast<uint8_t>(value);
        } else {
            rxLength_ = 0;  // Reject an overlong/noisy frame safely.
        }
        lastRxByteMs_ = millis();
    }

    if (rxLength_ == 0 || millis() - lastRxByteMs_ < kRtuFrameGapMs) return;
    handleFrame(snapshot);
    rxLength_ = 0;
}

uint16_t GldModbusRtu::crc16(const uint8_t* data, size_t length) const {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (uint8_t bit = 0; bit < 8; ++bit) {
            crc = (crc & 1U) ? static_cast<uint16_t>((crc >> 1) ^ 0xA001U)
                             : static_cast<uint16_t>(crc >> 1);
        }
    }
    return crc;
}

void GldModbusRtu::handleFrame(const GldModbusRtuSnapshot& snapshot) {
    if (rxLength_ != 8 || rxBuffer_[0] != unitId_) return;

    const uint16_t receivedCrc = static_cast<uint16_t>(rxBuffer_[6]) |
                                 static_cast<uint16_t>(rxBuffer_[7] << 8);
    if (crc16(rxBuffer_, 6) != receivedCrc) return;

    const uint8_t function = rxBuffer_[1];
    if (function != kFunctionReadHoldingRegisters &&
        function != kFunctionReadInputRegisters) {
        sendException(function, kExceptionIllegalFunction);
        return;
    }

    const uint16_t firstRegister = readBe16(&rxBuffer_[2]);
    const uint16_t registerCount = readBe16(&rxBuffer_[4]);
    if (registerCount == 0 || registerCount > kRegisterCount) {
        sendException(function, kExceptionIllegalValue);
        return;
    }
    if (firstRegister >= kRegisterCount ||
        static_cast<uint32_t>(firstRegister) + registerCount > kRegisterCount) {
        sendException(function, kExceptionIllegalAddress);
        return;
    }
    sendRegisters(function, firstRegister, registerCount, snapshot);
}

void GldModbusRtu::sendException(uint8_t function, uint8_t exceptionCode) {
    uint8_t response[5] = {unitId_, static_cast<uint8_t>(function | 0x80U), exceptionCode, 0, 0};
    const uint16_t crc = crc16(response, 3);
    response[3] = static_cast<uint8_t>(crc & 0xFFU);
    response[4] = static_cast<uint8_t>(crc >> 8);
    beginTransmit();
    serial_.write(response, sizeof(response));
    serial_.flush();
    endTransmit();
}

void GldModbusRtu::sendRegisters(uint8_t function, uint16_t firstRegister,
                                 uint16_t registerCount,
                                 const GldModbusRtuSnapshot& snapshot) {
    const uint16_t registers[kRegisterCount] = {
        snapshot.statusBits, snapshot.gasClass, snapshot.confidence,
        snapshot.batteryMv, snapshot.source24V, snapshot.externalPower,
        snapshot.txCounterLow, snapshot.nodeId,
    };
    uint8_t response[3 + (kRegisterCount * 2) + 2]{};
    response[0] = unitId_;
    response[1] = function;
    response[2] = static_cast<uint8_t>(registerCount * 2U);
    for (uint16_t index = 0; index < registerCount; ++index) {
        writeBe16(&response[3 + (index * 2U)], registers[firstRegister + index]);
    }
    const size_t payloadLength = 3U + (static_cast<size_t>(registerCount) * 2U);
    const uint16_t crc = crc16(response, payloadLength);
    response[payloadLength] = static_cast<uint8_t>(crc & 0xFFU);
    response[payloadLength + 1U] = static_cast<uint8_t>(crc >> 8);
    beginTransmit();
    serial_.write(response, payloadLength + 2U);
    serial_.flush();
    endTransmit();
}

void GldModbusRtu::beginTransmit() {
    digitalWrite(static_cast<uint8_t>(dirPin_), HIGH);
    delayMicroseconds(20);
}

void GldModbusRtu::endTransmit() {
    digitalWrite(static_cast<uint8_t>(dirPin_), LOW);
}

}  // namespace pgl::gld
