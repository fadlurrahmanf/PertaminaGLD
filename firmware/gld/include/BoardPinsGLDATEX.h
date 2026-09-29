#pragma once

#include "BoardPinsGLD3.h"

// GLD ATEX is a source-verified MotherBoardGLDVer2 derivative.  Its common
// GLD2 pinout and J3 fan path match the retained Ver2 map, but it intentionally
// has a dedicated namespace/profile so it is never selected by a GLD2 build.
namespace pgl::gld::board::gld_atex {

constexpr int PIN_SPI_SCK = gld3::PIN_SPI_SCK;
constexpr int PIN_SPI_MOSI = gld3::PIN_SPI_MOSI;
constexpr int PIN_SPI_MISO = gld3::PIN_SPI_MISO;
constexpr int PIN_ADS1256_CS = gld3::PIN_ADS1256_CS;
constexpr int PIN_ADS1256_DRDY = gld3::PIN_ADS1256_DRDY;
constexpr int PIN_ADS1256_RESET = gld3::PIN_ADS1256_RESET;
constexpr int PIN_ADS1256_PDOWN = gld3::PIN_ADS1256_PDOWN;
constexpr int PIN_LORA_CS = gld3::PIN_LORA_CS;
constexpr int PIN_LORA_RST = gld3::PIN_LORA_RST;
constexpr int PIN_LORA_BUSY = gld3::PIN_LORA_BUSY;
constexpr int PIN_LORA_DIO1 = gld3::PIN_LORA_DIO1;
constexpr int PIN_LORA_RXEN = gld3::PIN_LORA_RXEN;
constexpr int PIN_LORA_TXEN = gld3::PIN_LORA_TXEN;
constexpr int PIN_I2C_SDA = gld3::PIN_I2C_SDA;
constexpr int PIN_I2C_SCL = gld3::PIN_I2C_SCL;
constexpr int PIN_STATUS_LED = gld3::PIN_STATUS_LED;
constexpr int PIN_ALARM = gld3::PIN_ALARM;
constexpr int PIN_ALARM_ENABLE_BOOST = gld3::PIN_ALARM_ENABLE_BOOST;
// U49 GPIO7 -> R42 -> Q5 gate; Q5 is the low-side switch for J3/DC_FAN.
constexpr int PIN_DC_FAN = gld3::PIN_DC_FAN;
constexpr bool HAS_DC_FAN = gld3::HAS_DC_FAN;
constexpr int PIN_TPL5010_DONE = gld3::PIN_TPL5010_DONE;
constexpr int PIN_POWER_LATCH_CLR = gld3::PIN_POWER_LATCH_CLR;
constexpr int PIN_BATTERY_VOLTAGE = gld3::PIN_BATTERY_VOLTAGE;
constexpr int PIN_24V_POWER_GOOD = gld3::PIN_24V_POWER_GOOD;
constexpr int PIN_POWER_SOURCE_STATUS = gld3::PIN_POWER_SOURCE_STATUS;
constexpr int PIN_USER_BUTTON = gld3::PIN_USER_BUTTON;
constexpr int PIN_RS485_DIR = gld3::PIN_RS485_DIR;
constexpr int PIN_RS485_RX = gld3::PIN_RS485_RX;
constexpr int PIN_RS485_TX = gld3::PIN_RS485_TX;
constexpr bool HAS_RS485 = gld3::HAS_RS485;
constexpr uint8_t SENSOR_COUNT = gld3::SENSOR_COUNT;
constexpr const char* const* SENSOR_NAMES = gld3::SENSOR_NAMES;
constexpr const char* const* SENSOR_HEADERS = gld3::SENSOR_HEADERS;
constexpr uint8_t TCA9548A_ADDR = gld3::TCA9548A_ADDR;
constexpr uint8_t MCP4725_ADDR = gld3::MCP4725_ADDR;
constexpr uint8_t PCF8574_ADDR = gld3::PCF8574_ADDR;
constexpr uint8_t PCF8574_ALL_LOAD_SWITCHES_ON = gld3::PCF8574_ALL_LOAD_SWITCHES_ON;
constexpr uint8_t PCF8574_ALL_LOAD_SWITCHES_OFF = gld3::PCF8574_ALL_LOAD_SWITCHES_OFF;
constexpr uint16_t GLD_DAC_CODE_MIN = gld3::GLD_DAC_CODE_MIN;
constexpr uint16_t GLD_DAC_CODE_MAX = gld3::GLD_DAC_CODE_MAX;
constexpr const uint8_t* SENSOR_TO_MUX_CH = gld3::SENSOR_TO_MUX_CH;
constexpr const uint8_t* SENSOR_TO_POWER_EN = gld3::SENSOR_TO_POWER_EN;
constexpr const uint8_t* POWER_EN_TO_MUX_CH = gld3::POWER_EN_TO_MUX_CH;
constexpr const uint8_t* SENSOR_TO_ADS_CH = gld3::SENSOR_TO_ADS_CH;

static_assert(PIN_DC_FAN == 7 && HAS_DC_FAN, "GLD ATEX J3 fan must use GPIO7");
static_assert(PIN_RS485_DIR == 19 && PIN_RS485_RX == 20 && PIN_RS485_TX == 21,
              "GLD ATEX J4 RS-485 pin map mismatch");

}  // namespace pgl::gld::board::gld_atex
