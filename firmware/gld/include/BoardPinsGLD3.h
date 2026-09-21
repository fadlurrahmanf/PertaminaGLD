#pragma once

#include <cstdint>

// GLD3 is electrically GLD2-compatible except for the source-verified fan
// driver added in docs/wiring/Board_GLD3.zip. Keep this map separate so a
// GLD2 build never energises GPIO7 as a fan output.
namespace pgl::gld::board::gld3 {

constexpr int PIN_SPI_SCK = 12;
constexpr int PIN_SPI_MOSI = 11;
constexpr int PIN_SPI_MISO = 13;

constexpr int PIN_ADS1256_CS = 38;
constexpr int PIN_ADS1256_DRDY = 39;
constexpr int PIN_ADS1256_RESET = 48;
constexpr int PIN_ADS1256_PDOWN = 45;

constexpr int PIN_LORA_CS = 14;
constexpr int PIN_LORA_RST = 2;
constexpr int PIN_LORA_BUSY = 10;
constexpr int PIN_LORA_DIO1 = 1;
constexpr int PIN_LORA_RXEN = 41;
constexpr int PIN_LORA_TXEN = 42;

constexpr int PIN_I2C_SDA = 8;
constexpr int PIN_I2C_SCL = 9;

constexpr int PIN_STATUS_LED = 6;
constexpr int PIN_ALARM = 40;
constexpr int PIN_ALARM_ENABLE_BOOST = 15;
// U49 GPIO7 -> R42 -> Q5 AO3400A gate. Q5 is a low-side fan switch and R43
// pulls the gate LOW, so HIGH commands the fan ON and boot is safely OFF.
constexpr int PIN_DC_FAN = 7;
constexpr bool HAS_DC_FAN = true;

constexpr int PIN_TPL5010_DONE = 17;
constexpr int PIN_POWER_LATCH_CLR = 16;
constexpr int PIN_BATTERY_VOLTAGE = 4;
constexpr int PIN_24V_POWER_GOOD = 47;
constexpr int PIN_POWER_SOURCE_STATUS = 18;
constexpr int PIN_USER_BUTTON = 5;

constexpr int PIN_RS485_DIR = 19;
constexpr int PIN_RS485_RX = 20;
constexpr int PIN_RS485_TX = 21;
constexpr bool HAS_RS485 = true;

constexpr uint8_t SENSOR_COUNT = 8;
constexpr const char* SENSOR_NAMES[SENSOR_COUNT] = {
    "MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2",
};
constexpr const char* SENSOR_HEADERS[SENSOR_COUNT] = {
    "H2", "H1", "H3", "H4", "H5", "H6", "H7", "H8",
};

constexpr uint8_t TCA9548A_ADDR = 0x71;
constexpr uint8_t MCP4725_ADDR = 0x60;
constexpr uint8_t PCF8574_ADDR = 0x20;
constexpr uint8_t PCF8574_ALL_LOAD_SWITCHES_ON = 0xFF;
constexpr uint8_t PCF8574_ALL_LOAD_SWITCHES_OFF = 0x00;
constexpr uint16_t GLD_DAC_CODE_MIN = 0;
constexpr uint16_t GLD_DAC_CODE_MAX = 4095;
constexpr uint8_t SENSOR_TO_MUX_CH[SENSOR_COUNT] = {7, 6, 5, 4, 3, 2, 1, 0};
constexpr uint8_t SENSOR_TO_POWER_EN[SENSOR_COUNT] = {0, 6, 7, 3, 4, 5, 2, 1};
constexpr uint8_t POWER_EN_TO_MUX_CH[SENSOR_COUNT] = {7, 0, 1, 4, 3, 2, 6, 5};
constexpr uint8_t SENSOR_TO_ADS_CH[SENSOR_COUNT] = {0, 1, 2, 3, 4, 5, 6, 7};

}  // namespace pgl::gld::board::gld3
