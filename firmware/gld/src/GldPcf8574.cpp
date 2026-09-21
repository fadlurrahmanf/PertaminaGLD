#include "GldPcf8574.h"

#include <PCF8574.h>

#include "BoardPins.h"

namespace pgl::gld {

namespace {

bool readLivePort(TwoWire& i2c, uint8_t& outputs) {
    if (i2c.requestFrom(static_cast<int>(board::PCF8574_ADDR), 1) != 1 || !i2c.available()) {
        return false;
    }
    outputs = static_cast<uint8_t>(i2c.read());
    return true;
}

PCF8574::DigitalInput maskToPins(uint8_t outputs) {
    PCF8574::DigitalInput pins{};
    pins.p0 = (outputs & (1U << 0)) ? HIGH : LOW;
    pins.p1 = (outputs & (1U << 1)) ? HIGH : LOW;
    pins.p2 = (outputs & (1U << 2)) ? HIGH : LOW;
    pins.p3 = (outputs & (1U << 3)) ? HIGH : LOW;
    pins.p4 = (outputs & (1U << 4)) ? HIGH : LOW;
    pins.p5 = (outputs & (1U << 5)) ? HIGH : LOW;
    pins.p6 = (outputs & (1U << 6)) ? HIGH : LOW;
    pins.p7 = (outputs & (1U << 7)) ? HIGH : LOW;
    return pins;
}

}  // namespace

GldPcf8574::~GldPcf8574() {
    delete driver_;
}

bool GldPcf8574::begin(TwoWire& i2c) {
    i2c_ = &i2c;
    i2c_->begin(board::PIN_I2C_SDA, board::PIN_I2C_SCL);
#if defined(ARDUINO_ARCH_ESP32)
    i2c_->setTimeOut(50);
#endif
    // xreef's begin() writes the configured output start levels.  Capture the
    // physical mask first, then configure all EN pins to reproduce that same
    // mask so re-begin never changes the established TPS22919 power policy.
    uint8_t liveOutputs = outputs_;
    if (!readLivePort(*i2c_, liveOutputs)) {
        ready_ = false;
        return false;
    }
    delete driver_;
    driver_ = new PCF8574(i2c_, board::PCF8574_ADDR,
                          board::PIN_I2C_SDA, board::PIN_I2C_SCL);
    for (uint8_t pin = 0; pin < 8; ++pin) {
        driver_->pinMode(pin, OUTPUT, (liveOutputs & (1U << pin)) ? HIGH : LOW);
    }
    ready_ = driver_->begin();
    if (ready_) outputs_ = liveOutputs;
    return ready_;
}

bool GldPcf8574::writeOutputs(uint8_t outputs) {
    if (!ready_ || driver_ == nullptr) return false;
    if (!driver_->digitalWriteAll(maskToPins(outputs))) return false;
    outputs_ = outputs;
    return true;
}

bool GldPcf8574::readOutputs(uint8_t& outputs) {
    if (!ready_ || i2c_ == nullptr) return false;
    // The xreef API exposes output pins as its write cache.  Retain a direct
    // single-byte port read here so Nulling's safety gate remains a real PCF
    // level readback rather than a confirmation of the requested mask.
    if (!readLivePort(*i2c_, outputs)) return false;
    outputs_ = outputs;
    return true;
}

bool GldPcf8574::enableAllLoadSwitches() {
    // TPS22919 ON is active-HIGH; PCF bits P0..P7 map directly to EN0..EN7.
    return writeOutputs(board::PCF8574_ALL_LOAD_SWITCHES_ON);
}

}  // namespace pgl::gld
