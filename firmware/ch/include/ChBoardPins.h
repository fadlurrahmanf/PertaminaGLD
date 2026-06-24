#pragma once

#include <cstdint>

namespace pgl::ch::board {

constexpr uint8_t PIN_SPI_SCK = 12;
constexpr uint8_t PIN_SPI_MOSI = 11;
constexpr uint8_t PIN_SPI_MISO = 13;

constexpr uint8_t PIN_RADIO_A_TXEN = 5;
constexpr uint8_t PIN_RADIO_A_RXEN = 6;
constexpr uint8_t PIN_RADIO_A_RST = 7;
constexpr uint8_t PIN_RADIO_A_BUSY = 15;
constexpr uint8_t PIN_RADIO_A_DIO1 = 16;
constexpr uint8_t PIN_RADIO_A_CS = 17;

constexpr uint8_t PIN_RADIO_B_CS = 14;
constexpr uint8_t PIN_RADIO_B_BUSY = 38;
constexpr uint8_t PIN_RADIO_B_RXEN = 39;
constexpr uint8_t PIN_RADIO_B_TXEN = 40;
constexpr uint8_t PIN_RADIO_B_RST = 41;
constexpr uint8_t PIN_RADIO_B_DIO1 = 42;

constexpr uint8_t PIN_BATMON = 4;

}  // namespace pgl::ch::board
