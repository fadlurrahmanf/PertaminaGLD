#pragma once

#include <cstdint>

// source-CH_DualRadio_E220Ver4: board circle (besar).
namespace pgl::ch::board {

constexpr const char* BOARD_PROFILE = "circle";
constexpr uint8_t PIN_SPI_SCK = 12;
constexpr uint8_t PIN_SPI_MOSI = 11;
constexpr uint8_t PIN_SPI_MISO = 13;

constexpr uint8_t PIN_RADIO_A_TXEN = 5;
constexpr uint8_t PIN_RADIO_A_RXEN = 6;
constexpr uint8_t PIN_RADIO_A_RST = 7;
constexpr uint8_t PIN_RADIO_A_DIO1 = 15;
constexpr uint8_t PIN_RADIO_A_CS = 16;
constexpr uint8_t PIN_RADIO_A_BUSY = 17;

constexpr uint8_t PIN_RADIO_B_RXEN = 39;
constexpr uint8_t PIN_RADIO_B_TXEN = 40;
constexpr uint8_t PIN_RADIO_B_BUSY = 41;
constexpr uint8_t PIN_RADIO_B_CS = 42;
constexpr uint8_t PIN_RADIO_B_RST = 1;
constexpr uint8_t PIN_RADIO_B_DIO1 = 2;

constexpr uint8_t PIN_BATMON = 4;
constexpr uint8_t PIN_WDT_WAKE = 21;
constexpr uint8_t PIN_TPL5010_DONE = 47;
constexpr uint8_t PIN_WDT_KEEPALIVE = PIN_TPL5010_DONE;

}  // namespace pgl::ch::board
