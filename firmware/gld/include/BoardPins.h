#pragma once

#include <cstdint>

namespace pgl::gld::board {

constexpr uint8_t PIN_SPI_SCK = 12;
constexpr uint8_t PIN_SPI_MOSI = 11;
constexpr uint8_t PIN_SPI_MISO = 13;

constexpr uint8_t PIN_ADS1256_CS = 47;
constexpr uint8_t PIN_ADS1256_DRDY = 10;
constexpr uint8_t PIN_ADS1256_SYNC = 18;

constexpr uint8_t PIN_LORA_CS = 15;
constexpr uint8_t PIN_LORA_RST = 39;
constexpr uint8_t PIN_LORA_BUSY = 7;
constexpr uint8_t PIN_LORA_DIO1 = 40;
constexpr uint8_t PIN_LORA_RXEN = 5;
constexpr uint8_t PIN_LORA_TXEN = 6;

constexpr uint8_t PIN_I2C_SDA = 8;
constexpr uint8_t PIN_I2C_SCL = 9;

constexpr uint8_t PIN_STATUS_LED = 41;
constexpr uint8_t PIN_ALARM_LAMP = 1;
constexpr uint8_t PIN_BUZZER = 2;
constexpr uint8_t PIN_DC_FAN = 42;

constexpr uint8_t PIN_TPL5110_DONE = 14;
constexpr uint8_t PIN_BATTERY_VOLTAGE = 4;
constexpr uint8_t PIN_24V_POWER_GOOD = 45;
constexpr uint8_t PIN_USER_BUTTON = 16;

constexpr uint8_t SENSOR_COUNT = 8;
constexpr const char* SENSOR_NAMES[SENSOR_COUNT] = {
    "MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2",
};

constexpr uint8_t TCA9548A_ADDR = 0x71;
constexpr uint8_t MCP4725_ADDR = 0x60;
constexpr uint16_t GLD_DAC_CODE_MIN = 0;
constexpr uint16_t GLD_DAC_CODE_MAX = 4095;
constexpr uint16_t SENSOR_TO_MUX_CH[SENSOR_COUNT] = {7, 6, 5, 4, 3, 2, 0, 1};

}  // namespace pgl::gld::board
