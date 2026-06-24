#pragma once

#include <cstddef>
#include <cstdint>

namespace pgl::gld {

constexpr size_t GLD_SENSOR_MOVING_AVERAGE_WINDOW = 10;

class GldMovingAverage {
public:
    void reset();
    void resetChannel(uint8_t channel);
    float add(uint8_t channel, float value);
    float value(uint8_t channel) const;
    uint8_t count(uint8_t channel) const;

private:
    float buffer_[8][GLD_SENSOR_MOVING_AVERAGE_WINDOW]{};
    float sum_[8]{};
    uint8_t index_[8]{};
    uint8_t count_[8]{};
};

}  // namespace pgl::gld
