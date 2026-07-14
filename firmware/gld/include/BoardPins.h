#pragma once

#include <cstdint>

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

constexpr int PIN_TPL5110_DONE = PGL_GLD_PIN_TPL5110_DONE;
constexpr int PIN_POWER_LATCH_CLR = PGL_GLD_PIN_POWER_LATCH_CLR;
constexpr int PIN_BATTERY_VOLTAGE = PGL_GLD_PIN_BATTERY_VOLTAGE;
constexpr int PIN_24V_POWER_GOOD = PGL_GLD_PIN_24V_POWER_GOOD;
constexpr int PIN_USER_BUTTON = PGL_GLD_PIN_USER_BUTTON;

constexpr uint8_t SENSOR_COUNT = 8;
constexpr const char* SENSOR_NAMES[SENSOR_COUNT] = {
    "MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2",
};

constexpr uint8_t TCA9548A_ADDR = 0x71;
constexpr uint8_t MCP4725_ADDR = 0x60;
constexpr uint16_t GLD_DAC_CODE_MIN = 0;
constexpr uint16_t GLD_DAC_CODE_MAX = 4095;
constexpr uint8_t SENSOR_TO_MUX_CH[SENSOR_COUNT] = {7, 6, 5, 0, 1, 2, 3, 4};
constexpr uint8_t SENSOR_TO_ADS_CH[SENSOR_COUNT] = {0, 1, 2, 3, 4, 5, 6, 7};

}  // namespace pgl::gld::board
