#pragma once

#include <cstdint>

// Source_CH_Board_Kecil / dualRadioCH_E220Ver5: board rectangle (kecil).
// Gateway uses Radio B and keeps Radio A disabled.
namespace pgl::gateway::board {

constexpr const char* BOARD_PROFILE = "rectangle";
constexpr uint8_t PIN_SPI_SCK = 12;
constexpr uint8_t PIN_SPI_MOSI = 11;
constexpr uint8_t PIN_SPI_MISO = 13;

constexpr uint8_t PIN_RADIO_UNUSED_A_TXEN = 5;
constexpr uint8_t PIN_RADIO_UNUSED_A_RXEN = 6;
constexpr uint8_t PIN_RADIO_UNUSED_A_CS = 7;
constexpr uint8_t PIN_RADIO_UNUSED_A_RST = 16;

constexpr uint8_t PIN_RADIO_B_CS = 39;
constexpr uint8_t PIN_RADIO_B_BUSY = 40;
constexpr uint8_t PIN_RADIO_B_DIO1 = 41;
constexpr uint8_t PIN_RADIO_B_RXEN = 42;
constexpr uint8_t PIN_RADIO_B_TXEN = 2;
constexpr uint8_t PIN_RADIO_B_RST = 1;

constexpr uint8_t PIN_STATUS_LED = 20;

}  // namespace pgl::gateway::board
