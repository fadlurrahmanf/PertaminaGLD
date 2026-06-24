#pragma once

#include <cstdint>

namespace pgl::config::lora::star {

// -----------------------------------------------------------------------------
// Editable parameters
// -----------------------------------------------------------------------------

// Frekuensi carrier LoRa STAR dalam MHz. Harus sama antara GLD dan radio STAR CH.
// Ubah hanya jika channel STAR dipindah dan pastikan tetap dalam alokasi 920-923 MHz.
constexpr float FREQ_MHZ = 920.0f;

// Bandwidth LoRa STAR dalam kHz. 125 kHz memberi kompromi umum antara airtime,
// sensitivitas, dan kompatibilitas dengan setting CH yang sudah diuji.
constexpr float BW_KHZ = 125.0f;

// Spreading factor LoRa STAR. SF7 dipilih agar uplink banyak GLD tetap cepat.
// Menaikkan SF menambah jangkauan tetapi memperpanjang airtime.
constexpr uint8_t SF = 7;

// Coding rate RadioLib untuk STAR. Nilai 5 berarti CR 4/5.
// Ubah hanya jika kedua sisi link STAR diubah bersama.
constexpr uint8_t CR = 5;

// Sync word domain STAR. Harus sama di GLD dan CH STAR, serta berbeda dari MESH
// agar paket STAR dan MESH tidak saling diterima.
constexpr uint8_t SYNC_WORD = 0x12;

// Daya transmit STAR dalam dBm. Dipakai GLD saat mengirim ke CH.
// Sesuaikan dengan regulasi, jarak bench/lapangan, dan budget daya GLD.
constexpr int8_t TX_POWER_DBM = 17;

// Preamble LoRa STAR. Harus kompatibel di GLD dan CH.
// Nilai 8 adalah default bench yang umum dan cepat.
constexpr uint16_t PREAMBLE = 8;

// Tegangan TCXO untuk board/radio yang memakai TCXO. Dipakai sebagai percobaan
// init pertama pada SX1262. Jika board tidak butuh TCXO, fallback XTAL dipakai.
constexpr float TCXO_VOLTAGE = 1.6f;

// Tegangan TCXO fallback untuk mode XTAL/non-TCXO. Nilai 0.0 dipakai ketika
// init TCXO gagal atau board memakai kristal biasa.
constexpr float XTAL_TCXO_VOLTAGE = 0.0f;

// Kecepatan SPI radio STAR dalam Hz. Harus stabil untuk wiring dan board saat ini.
// Terlalu tinggi dapat membuat init/transfer radio tidak stabil.
constexpr uint32_t SPI_HZ = 2000000;

// -----------------------------------------------------------------------------
// Derived / aliases
// -----------------------------------------------------------------------------
// None yet. Add aliases here if another config value follows this file.

}  // namespace pgl::config::lora::star
