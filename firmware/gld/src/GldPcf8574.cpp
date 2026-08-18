#include "GldPcf8574.h"

#include "BoardPins.h"

namespace pgl::gld {

bool GldPcf8574::begin(TwoWire& i2c) {
    i2c_ = &i2c;
    i2c_->begin(board::PIN_I2C_SDA, board::PIN_I2C_SCL);
#if defined(ARDUINO_ARCH_ESP32)
    i2c_->setTimeOut(50);
#endif
    i2c_->beginTransmission(board::PCF8574_ADDR);
    ready_ = i2c_->endTransmission() == 0;
    return ready_;
}

bool GldPcf8574::writeOutputs(uint8_t outputs) {
    if (!ready_ || i2c_ == nullptr) return false;
    i2c_->beginTransmission(board::PCF8574_ADDR);
    i2c_->write(outputs);
    if (i2c_->endTransmission() != 0) return false;
    outputs_ = outputs;
    return true;
}

bool GldPcf8574::enableAllLoadSwitches() {
    // TPS22919 ON is active-HIGH; PCF bits P0..P7 map directly to EN0..EN7.
    return writeOutputs(board::PCF8574_ALL_LOAD_SWITCHES_ON);
}

}  // namespace pgl::gld
