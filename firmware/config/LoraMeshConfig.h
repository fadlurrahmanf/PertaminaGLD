#pragma once

#include <cstdint>

namespace pgl::config::lora::mesh {

// -----------------------------------------------------------------------------
// Editable parameters
// -----------------------------------------------------------------------------

// Frekuensi carrier LoRa MESH dalam MHz. Harus sama antara CH MESH dan Gateway.
// Dipisahkan dari STAR agar dua domain radio tidak saling mengganggu.
constexpr float FREQ_MHZ = 921.0f;

// Bandwidth LoRa MESH dalam kHz. 125 kHz menjaga link backbone stabil sambil
// tetap kompatibel dengan setting bench Gateway/CH.
constexpr float BW_KHZ = 125.0f;

// Spreading factor LoRa MESH. SF9 memberi margin link lebih besar untuk backbone
// CH-Gateway/CH-CH, dengan airtime lebih panjang daripada STAR SF7.
constexpr uint8_t SF = 9;

// Coding rate RadioLib untuk MESH. Nilai 5 berarti CR 4/5.
// Harus sama di CH dan Gateway.
constexpr uint8_t CR = 5;

// Sync word domain MESH. Harus sama di CH MESH dan Gateway, serta berbeda dari
// STAR sync word.
constexpr uint8_t SYNC_WORD = 0x34;

// Daya transmit MESH dalam dBm. Dipakai CH dan Gateway untuk backbone.
// Sesuaikan dengan regulasi, link budget, dan konsumsi daya CH.
constexpr int8_t TX_POWER_DBM = 17;

// Preamble LoRa MESH. Harus kompatibel di semua node backbone.
constexpr uint16_t PREAMBLE = 8;

// Tegangan TCXO untuk init radio MESH pertama. Nilai ini mengikuti board SX1262
// yang memakai TCXO 1.6 V pada bench saat ini.
constexpr float TCXO_VOLTAGE = 1.6f;

// Tegangan TCXO fallback untuk mode XTAL/non-TCXO. Nilai 0.0 dipakai ketika
// init TCXO gagal atau board memakai kristal biasa.
constexpr float XTAL_TCXO_VOLTAGE = 0.0f;

// Kecepatan SPI radio MESH dalam Hz. Harus stabil untuk wiring CH/Gateway.
// Terlalu tinggi dapat memicu error SPI atau radio tidak terdeteksi.
constexpr uint32_t SPI_HZ = 2000000;

// -----------------------------------------------------------------------------
// Derived / aliases
// -----------------------------------------------------------------------------
// None yet. Add aliases here if another config value follows this file.

}  // namespace pgl::config::lora::mesh
