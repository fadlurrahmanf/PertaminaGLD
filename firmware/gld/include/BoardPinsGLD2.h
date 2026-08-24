#pragma once

#include <cstdint>

// Standalone pin map for docs/wiring/gld-project-ver2-2026-07-01/source-GLD2.zip.
// This header is intentionally not included by the active firmware.  It is a
// separate source-of-truth for a later dedicated GLD2 build profile.
namespace pgl::gld::board::gld2 {

constexpr int PIN_SPI_SCK = 12;
constexpr int PIN_SPI_MOSI = 11;
constexpr int PIN_SPI_MISO = 13;

constexpr int PIN_ADS1256_CS = 38;
constexpr int PIN_ADS1256_DRDY = 39;
// ADS1256 has dedicated active-low RESET and PDWN nets on GLD2.
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
// GPIO40 drives R94 into the Q4 (AO3400A) gate. R41 pulls the gate down, so
// HIGH asserts the low-side alarm load; this is not an active-low signal.
constexpr int PIN_ALARM = 40;
// TPS61088 EN: required before the external alarm load is energised.
constexpr int PIN_ALARM_ENABLE_BOOST = 15;
constexpr int PIN_DC_FAN = -1;
constexpr bool HAS_DC_FAN = false;

constexpr int PIN_TPL5010_DONE = 17;
constexpr int PIN_POWER_LATCH_CLR = 16;
constexpr int PIN_BATTERY_VOLTAGE = 4;
constexpr int PIN_24V_POWER_GOOD = 47;
// ST_P reports the selected input source: HIGH = 24 V, LOW = battery.
constexpr int PIN_POWER_SOURCE_STATUS = 18;
constexpr int PIN_USER_BUTTON = 5;

// U47 THVD1410DR half-duplex RS-485 interface.
constexpr int PIN_RS485_DIR = 19;
constexpr int PIN_RS485_RX = 20;
constexpr int PIN_RS485_TX = 21;
constexpr bool HAS_RS485 = true;

constexpr uint8_t SENSOR_COUNT = 8;
constexpr const char* SENSOR_NAMES[SENSOR_COUNT] = {
    "MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2",
};
// Sensor order is also the verified physical header/scan order.
constexpr const char* SENSOR_HEADERS[SENSOR_COUNT] = {
    "H2", "H1", "H3", "H4", "H5", "H6", "H7", "H8",
};

constexpr uint8_t TCA9548A_ADDR = 0x71;
constexpr uint8_t MCP4725_ADDR = 0x60;
// U12: PCF8574T/TR, A0/A1/A2 tied to GND. P0..P7 drive EN0..EN7.
constexpr uint8_t PCF8574_ADDR = 0x20;
constexpr uint8_t PCF8574_ALL_LOAD_SWITCHES_ON = 0xFF;
constexpr uint8_t PCF8574_ALL_LOAD_SWITCHES_OFF = 0x00;
constexpr uint16_t GLD_DAC_CODE_MIN = 0;
constexpr uint16_t GLD_DAC_CODE_MAX = 4095;
// Authoritative physical header order (left-to-right):
// H2 MQ8 EN0 AIN0 TCA7; H1 MQ135 EN6 AIN1 TCA6;
// H3 MQ3 EN7 AIN2 TCA5; H4 MQ5 EN3 AIN3 TCA4;
// H5 MQ4 EN4 AIN4 TCA3; H6 MQ7 EN5 AIN5 TCA2;
// H7 MQ6 EN2 AIN6 TCA1; H8 MQ2 EN1 AIN7 TCA0.
constexpr uint8_t SENSOR_TO_MUX_CH[SENSOR_COUNT] = {7, 6, 5, 4, 3, 2, 1, 0};
// Operator-confirmed PCF8574 EN mapping, in SENSOR_NAMES order:
// MQ8->EN0, MQ135->EN6, MQ3->EN7, MQ5->EN3, MQ4->EN4, MQ7->EN5,
// MQ6->EN2, MQ2->EN1. This is independent of the TCA/MCP mapping above.
constexpr uint8_t SENSOR_TO_POWER_EN[SENSOR_COUNT] = {0, 6, 7, 3, 4, 5, 2, 1};
// EN-order mapping for the one-header-at-a-time boot scanner:
// EN0->TCA7, EN1->TCA0, EN2->TCA1, EN3->TCA4,
// EN4->TCA3, EN5->TCA2, EN6->TCA6, EN7->TCA5.
constexpr uint8_t POWER_EN_TO_MUX_CH[SENSOR_COUNT] = {7, 0, 1, 4, 3, 2, 6, 5};
// Operator-confirmed ADS1256 AIN mapping, in SENSOR_NAMES order:
// MQ8->AIN0, MQ135->AIN1, MQ3->AIN2, MQ5->AIN3, MQ4->AIN4, MQ7->AIN5,
// MQ6->AIN6, MQ2->AIN7.
constexpr uint8_t SENSOR_TO_ADS_CH[SENSOR_COUNT] = {0, 1, 2, 3, 4, 5, 6, 7};

}  // namespace pgl::gld::board::gld2
