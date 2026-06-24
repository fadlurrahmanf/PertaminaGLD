#include "GldMovingAverage.h"

namespace pgl::gld {

void GldMovingAverage::reset() {
    for (uint8_t ch = 0; ch < 8; ++ch) {
        resetChannel(ch);
    }
}

void GldMovingAverage::resetChannel(uint8_t channel) {
    if (channel >= 8) {
        return;
    }
    for (size_t i = 0; i < GLD_SENSOR_MOVING_AVERAGE_WINDOW; ++i) {
        buffer_[channel][i] = 0.0f;
    }
    sum_[channel] = 0.0f;
    index_[channel] = 0;
    count_[channel] = 0;
}

float GldMovingAverage::add(uint8_t channel, float valueIn) {
    if (channel >= 8) {
        return 0.0f;
    }

    if (count_[channel] < GLD_SENSOR_MOVING_AVERAGE_WINDOW) {
        buffer_[channel][index_[channel]] = valueIn;
        sum_[channel] += valueIn;
        ++count_[channel];
    } else {
        sum_[channel] -= buffer_[channel][index_[channel]];
        buffer_[channel][index_[channel]] = valueIn;
        sum_[channel] += valueIn;
    }

    index_[channel] = static_cast<uint8_t>((index_[channel] + 1) % GLD_SENSOR_MOVING_AVERAGE_WINDOW);
    return value(channel);
}

float GldMovingAverage::value(uint8_t channel) const {
    if (channel >= 8 || count_[channel] == 0) {
        return 0.0f;
    }
    return sum_[channel] / static_cast<float>(count_[channel]);
}

uint8_t GldMovingAverage::count(uint8_t channel) const {
    return channel < 8 ? count_[channel] : 0;
}

}  // namespace pgl::gld
