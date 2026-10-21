#pragma once
#include <cstdint>
namespace pgl::gld::board {
constexpr uint8_t SENSOR_COUNT = 8;
constexpr uint16_t GLD_DAC_CODE_MIN = 0, GLD_DAC_CODE_MAX = 4095;
constexpr uint8_t MCP4725_ADDR = 0x60;
constexpr uint8_t SENSOR_TO_MUX_CH[8] = {0,1,2,3,4,5,6,7};
constexpr const char* SENSOR_NAMES[8] = {"MQ8","MQ135","MQ3","MQ5","MQ4","MQ7","MQ6","MQ2"};
}
