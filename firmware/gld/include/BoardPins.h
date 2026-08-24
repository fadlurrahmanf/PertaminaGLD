#pragma once

#include <cstdint>

#ifndef PGL_GLD_BOARD_PROFILE_GLD2
#define PGL_GLD_BOARD_PROFILE_GLD2 0
#endif

#if PGL_GLD_BOARD_PROFILE_GLD2

#include "BoardPinsGLD2.h"

// The production runtime consumes pgl::gld::board. Keep this facade thin so
// BoardPinsGLD2.h remains the source of the GLD2 schematic pin map.
namespace pgl::gld::board {
constexpr int PIN_SPI_SCK = gld2::PIN_SPI_SCK;
constexpr int PIN_SPI_MOSI = gld2::PIN_SPI_MOSI;
constexpr int PIN_SPI_MISO = gld2::PIN_SPI_MISO;
constexpr int PIN_ADS1256_CS = gld2::PIN_ADS1256_CS;
constexpr int PIN_ADS1256_DRDY = gld2::PIN_ADS1256_DRDY;
constexpr int PIN_ADS1256_RESET = gld2::PIN_ADS1256_RESET;
constexpr int PIN_ADS1256_PDOWN = gld2::PIN_ADS1256_PDOWN;
constexpr int PIN_ADS1256_SYNC = PIN_ADS1256_PDOWN;
constexpr int PIN_LORA_CS = gld2::PIN_LORA_CS;
constexpr int PIN_LORA_RST = gld2::PIN_LORA_RST;
constexpr int PIN_LORA_BUSY = gld2::PIN_LORA_BUSY;
constexpr int PIN_LORA_DIO1 = gld2::PIN_LORA_DIO1;
constexpr int PIN_LORA_RXEN = gld2::PIN_LORA_RXEN;
constexpr int PIN_LORA_TXEN = gld2::PIN_LORA_TXEN;
constexpr int PIN_I2C_SDA = gld2::PIN_I2C_SDA;
constexpr int PIN_I2C_SCL = gld2::PIN_I2C_SCL;
constexpr int PIN_STATUS_LED = gld2::PIN_STATUS_LED;
constexpr int PIN_ALARM_LAMP = gld2::PIN_ALARM;
constexpr int PIN_BUZZER = -1;
constexpr int PIN_DC_FAN = gld2::PIN_DC_FAN;
constexpr bool HAS_DC_FAN = gld2::HAS_DC_FAN;
constexpr int PIN_TPL5110_DONE = gld2::PIN_TPL5010_DONE;
constexpr int PIN_POWER_LATCH_CLR = gld2::PIN_POWER_LATCH_CLR;
constexpr int PIN_BATTERY_VOLTAGE = gld2::PIN_BATTERY_VOLTAGE;
constexpr int PIN_24V_POWER_GOOD = gld2::PIN_24V_POWER_GOOD;
constexpr int PIN_POWER_SOURCE_STATUS = gld2::PIN_POWER_SOURCE_STATUS;
constexpr int PIN_USER_BUTTON = gld2::PIN_USER_BUTTON;
constexpr int PIN_RS485_DIR = gld2::PIN_RS485_DIR;
constexpr int PIN_RS485_RX = gld2::PIN_RS485_RX;
constexpr int PIN_RS485_TX = gld2::PIN_RS485_TX;
constexpr bool HAS_RS485 = gld2::HAS_RS485;
constexpr uint8_t SENSOR_COUNT = gld2::SENSOR_COUNT;
constexpr const char* const* SENSOR_NAMES = gld2::SENSOR_NAMES;
constexpr const char* const* SENSOR_HEADERS = gld2::SENSOR_HEADERS;
constexpr uint8_t TCA9548A_ADDR = gld2::TCA9548A_ADDR;
constexpr uint8_t MCP4725_ADDR = gld2::MCP4725_ADDR;
constexpr uint8_t PCF8574_ADDR = gld2::PCF8574_ADDR;
constexpr uint8_t PCF8574_ALL_LOAD_SWITCHES_ON = gld2::PCF8574_ALL_LOAD_SWITCHES_ON;
constexpr uint8_t PCF8574_ALL_LOAD_SWITCHES_OFF = gld2::PCF8574_ALL_LOAD_SWITCHES_OFF;
constexpr bool HAS_PCF8574 = true;
constexpr uint16_t GLD_DAC_CODE_MIN = gld2::GLD_DAC_CODE_MIN;
constexpr uint16_t GLD_DAC_CODE_MAX = gld2::GLD_DAC_CODE_MAX;
constexpr const uint8_t* SENSOR_TO_MUX_CH = gld2::SENSOR_TO_MUX_CH;
constexpr const uint8_t* SENSOR_TO_POWER_EN = gld2::SENSOR_TO_POWER_EN;
constexpr const uint8_t* POWER_EN_TO_MUX_CH = gld2::POWER_EN_TO_MUX_CH;
constexpr const uint8_t* SENSOR_TO_ADS_CH = gld2::SENSOR_TO_ADS_CH;
}  // namespace pgl::gld::board

#else

#ifndef PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8
#define PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8 0
#endif

#if PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8
#ifndef PGL_GLD_PIN_LORA_CS
#define PGL_GLD_PIN_LORA_CS 7
#endif
#ifndef PGL_GLD_PIN_LORA_RST
#define PGL_GLD_PIN_LORA_RST 2
#endif
#ifndef PGL_GLD_PIN_LORA_BUSY
#define PGL_GLD_PIN_LORA_BUSY 15
#endif
#ifndef PGL_GLD_PIN_LORA_DIO1
#define PGL_GLD_PIN_LORA_DIO1 1
#endif
#ifndef PGL_GLD_PIN_LORA_RXEN
#define PGL_GLD_PIN_LORA_RXEN 5
#endif
#ifndef PGL_GLD_PIN_LORA_TXEN
#define PGL_GLD_PIN_LORA_TXEN 6
#endif
#ifndef PGL_GLD_PIN_ALARM_LAMP
#define PGL_GLD_PIN_ALARM_LAMP 41
#endif
#ifndef PGL_GLD_PIN_BUZZER
#define PGL_GLD_PIN_BUZZER 40
#endif
#ifndef PGL_GLD_PIN_STATUS_LED
#define PGL_GLD_PIN_STATUS_LED 39
#endif
#endif

namespace pgl::gld::board {

#ifndef PGL_GLD_PIN_SPI_SCK
#define PGL_GLD_PIN_SPI_SCK 12
#endif
#ifndef PGL_GLD_PIN_SPI_MOSI
#define PGL_GLD_PIN_SPI_MOSI 11
#endif
#ifndef PGL_GLD_PIN_SPI_MISO
#define PGL_GLD_PIN_SPI_MISO 13
#endif

#ifndef PGL_GLD_PIN_ADS1256_CS
#define PGL_GLD_PIN_ADS1256_CS 47
#endif
#ifndef PGL_GLD_PIN_ADS1256_DRDY
#define PGL_GLD_PIN_ADS1256_DRDY 10
#endif
#ifndef PGL_GLD_PIN_ADS1256_SYNC
#define PGL_GLD_PIN_ADS1256_SYNC 18
#endif

#ifndef PGL_GLD_PIN_LORA_CS
#define PGL_GLD_PIN_LORA_CS 15
#endif
#ifndef PGL_GLD_PIN_LORA_RST
#define PGL_GLD_PIN_LORA_RST 39
#endif
#ifndef PGL_GLD_PIN_LORA_BUSY
#define PGL_GLD_PIN_LORA_BUSY 7
#endif
#ifndef PGL_GLD_PIN_LORA_DIO1
#define PGL_GLD_PIN_LORA_DIO1 40
#endif
#ifndef PGL_GLD_PIN_LORA_RXEN
#define PGL_GLD_PIN_LORA_RXEN 5
#endif
#ifndef PGL_GLD_PIN_LORA_TXEN
#define PGL_GLD_PIN_LORA_TXEN 6
#endif

#ifndef PGL_GLD_PIN_I2C_SDA
#define PGL_GLD_PIN_I2C_SDA 8
#endif
#ifndef PGL_GLD_PIN_I2C_SCL
#define PGL_GLD_PIN_I2C_SCL 9
#endif

#ifndef PGL_GLD_PIN_STATUS_LED
#define PGL_GLD_PIN_STATUS_LED 41
#endif
#ifndef PGL_GLD_PIN_ALARM_LAMP
#define PGL_GLD_PIN_ALARM_LAMP 1
#endif
#ifndef PGL_GLD_PIN_BUZZER
#define PGL_GLD_PIN_BUZZER 2
#endif
#ifndef PGL_GLD_PIN_DC_FAN
#define PGL_GLD_PIN_DC_FAN 42
#endif

#ifndef PGL_GLD_PIN_TPL5110_DONE
#define PGL_GLD_PIN_TPL5110_DONE 14
#endif
// Active-low CLR input of the SN74AUP1G74 power-latch flip-flop. Pulsing this
// HIGH->LOW->HIGH clears the latch and cuts ESP32 power (shared with the
// "clear latched alarm error" button function - see design.md §3.18).
#ifndef PGL_GLD_PIN_POWER_LATCH_CLR
#define PGL_GLD_PIN_POWER_LATCH_CLR 38
#endif
#ifndef PGL_GLD_PIN_BATTERY_VOLTAGE
#define PGL_GLD_PIN_BATTERY_VOLTAGE 4
#endif
#ifndef PGL_GLD_PIN_24V_POWER_GOOD
#define PGL_GLD_PIN_24V_POWER_GOOD 45
#endif
#ifndef PGL_GLD_PIN_USER_BUTTON
#define PGL_GLD_PIN_USER_BUTTON 16
#endif

constexpr int PIN_SPI_SCK = PGL_GLD_PIN_SPI_SCK;
constexpr int PIN_SPI_MOSI = PGL_GLD_PIN_SPI_MOSI;
constexpr int PIN_SPI_MISO = PGL_GLD_PIN_SPI_MISO;

constexpr int PIN_ADS1256_CS = PGL_GLD_PIN_ADS1256_CS;
constexpr int PIN_ADS1256_DRDY = PGL_GLD_PIN_ADS1256_DRDY;
constexpr int PIN_ADS1256_SYNC = PGL_GLD_PIN_ADS1256_SYNC;
constexpr int PIN_ADS1256_RESET = -1;
constexpr int PIN_ADS1256_PDOWN = PIN_ADS1256_SYNC;

constexpr int PIN_LORA_CS = PGL_GLD_PIN_LORA_CS;
constexpr int PIN_LORA_RST = PGL_GLD_PIN_LORA_RST;
constexpr int PIN_LORA_BUSY = PGL_GLD_PIN_LORA_BUSY;
constexpr int PIN_LORA_DIO1 = PGL_GLD_PIN_LORA_DIO1;
constexpr int PIN_LORA_RXEN = PGL_GLD_PIN_LORA_RXEN;
constexpr int PIN_LORA_TXEN = PGL_GLD_PIN_LORA_TXEN;

constexpr int PIN_I2C_SDA = PGL_GLD_PIN_I2C_SDA;
constexpr int PIN_I2C_SCL = PGL_GLD_PIN_I2C_SCL;

constexpr int PIN_STATUS_LED = PGL_GLD_PIN_STATUS_LED;
constexpr int PIN_ALARM_LAMP = PGL_GLD_PIN_ALARM_LAMP;
constexpr int PIN_BUZZER = PGL_GLD_PIN_BUZZER;
constexpr int PIN_DC_FAN = PGL_GLD_PIN_DC_FAN;
constexpr bool HAS_DC_FAN = PIN_DC_FAN >= 0;

constexpr int PIN_TPL5110_DONE = PGL_GLD_PIN_TPL5110_DONE;
constexpr int PIN_POWER_LATCH_CLR = PGL_GLD_PIN_POWER_LATCH_CLR;
constexpr int PIN_BATTERY_VOLTAGE = PGL_GLD_PIN_BATTERY_VOLTAGE;
constexpr int PIN_24V_POWER_GOOD = PGL_GLD_PIN_24V_POWER_GOOD;
constexpr int PIN_POWER_SOURCE_STATUS = -1;
constexpr int PIN_USER_BUTTON = PGL_GLD_PIN_USER_BUTTON;
constexpr int PIN_RS485_DIR = -1;
constexpr int PIN_RS485_RX = -1;
constexpr int PIN_RS485_TX = -1;
constexpr bool HAS_RS485 = false;

constexpr uint8_t SENSOR_COUNT = 8;
constexpr const char* SENSOR_NAMES[SENSOR_COUNT] = {
    "MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2",
};

constexpr uint8_t TCA9548A_ADDR = 0x71;
constexpr uint8_t MCP4725_ADDR = 0x60;
constexpr uint8_t PCF8574_ADDR = 0;
constexpr uint8_t PCF8574_ALL_LOAD_SWITCHES_ON = 0;
constexpr uint8_t PCF8574_ALL_LOAD_SWITCHES_OFF = 0;
constexpr bool HAS_PCF8574 = false;
constexpr uint16_t GLD_DAC_CODE_MIN = 0;
constexpr uint16_t GLD_DAC_CODE_MAX = 4095;
constexpr uint8_t SENSOR_TO_MUX_CH[SENSOR_COUNT] = {7, 6, 5, 0, 1, 2, 3, 4};
constexpr uint8_t SENSOR_TO_POWER_EN[SENSOR_COUNT] = {0, 6, 7, 3, 4, 5, 2, 1};
constexpr uint8_t SENSOR_TO_ADS_CH[SENSOR_COUNT] = {0, 1, 2, 3, 4, 5, 6, 7};

}  // namespace pgl::gld::board

#endif  // PGL_GLD_BOARD_PROFILE_GLD2
