#pragma once

#include <cstdint>

// source-CH_DualRadio_E220Ver4: board circle (besar). Gateway uses Radio B.
namespace pgl::gateway::board {

constexpr const char* BOARD_PROFILE = "circle";
constexpr uint8_t PIN_SPI_SCK = 12;
constexpr uint8_t PIN_SPI_MOSI = 11;
constexpr uint8_t PIN_SPI_MISO = 13;

constexpr uint8_t PIN_RADIO_UNUSED_A_TXEN = 5;
constexpr uint8_t PIN_RADIO_UNUSED_A_RXEN = 6;
constexpr uint8_t PIN_RADIO_UNUSED_A_RST = 7;
constexpr uint8_t PIN_RADIO_UNUSED_A_CS = 16;

constexpr uint8_t PIN_RADIO_B_RXEN = 39;
constexpr uint8_t PIN_RADIO_B_TXEN = 40;
constexpr uint8_t PIN_RADIO_B_BUSY = 41;
constexpr uint8_t PIN_RADIO_B_CS = 42;
constexpr uint8_t PIN_RADIO_B_RST = 1;
constexpr uint8_t PIN_RADIO_B_DIO1 = 2;

constexpr uint8_t PIN_STATUS_LED = 19;

}  // namespace pgl::gateway::board
