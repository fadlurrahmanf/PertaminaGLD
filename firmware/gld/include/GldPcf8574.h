#pragma once

#include <cstdint>

#include <Wire.h>

namespace pgl::gld {

class GldPcf8574 {
public:
    bool begin(TwoWire& i2c = Wire);
    bool writeOutputs(uint8_t outputs);
    bool enableAllLoadSwitches();
    bool ready() const { return ready_; }
    uint8_t outputs() const { return outputs_; }

private:
    TwoWire* i2c_ = nullptr;
    bool ready_ = false;
    uint8_t outputs_ = 0;
};

}  // namespace pgl::gld
