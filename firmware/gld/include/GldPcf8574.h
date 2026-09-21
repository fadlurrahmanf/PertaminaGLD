#pragma once

#include <cstdint>

#include <Wire.h>

class PCF8574;

namespace pgl::gld {

class GldPcf8574 {
public:
    ~GldPcf8574();
    bool begin(TwoWire& i2c = Wire);
    bool writeOutputs(uint8_t outputs);
    // Reads the live PCF port level without changing any EN output.
    bool readOutputs(uint8_t& outputs);
    bool enableAllLoadSwitches();
    bool ready() const { return ready_; }
    uint8_t outputs() const { return outputs_; }

private:
    TwoWire* i2c_ = nullptr;
    ::PCF8574* driver_ = nullptr;
    bool ready_ = false;
    uint8_t outputs_ = 0;
};

}  // namespace pgl::gld
