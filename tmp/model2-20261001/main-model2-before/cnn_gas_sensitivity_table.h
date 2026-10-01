// Tabel sensitivitas sensor MQ vs kelompok gas target, dari karakteristik umum datasheet MQ
// PENTING: nilai 0-3 estimasi kualitatif, sebaiknya disesuaikan dgn datasheet asli tiap sensor kalau ada.
// Baris = urutan CNN_GAS_ADC_NAMES, Kolom = urutan CNN_GAS_EVIDENCE_NAMES
#ifndef CNN_GAS_SENSITIVITY_TABLE_H
#define CNN_GAS_SENSITIVITY_TABLE_H

static const float CNN_GAS_SENSITIVITY_TABLE[CNN_GAS_N_ADC][CNN_GAS_N_EVIDENCE] = {
  { 0.0f, 1.0f, 1.0f, 3.0f, 0.0f, 0.0f, 0.0f },  // MQ8
  { 1.0f, 1.0f, 1.0f, 0.0f, 1.0f, 3.0f, 2.0f },  // MQ135
  { 0.0f, 0.0f, 0.0f, 0.0f, 3.0f, 1.0f, 1.0f },  // MQ3
  { 3.0f, 2.0f, 1.0f, 1.0f, 1.0f, 0.0f, 1.0f },  // MQ5
  { 2.0f, 3.0f, 1.0f, 1.0f, 0.0f, 0.0f, 1.0f },  // MQ4
  { 1.0f, 1.0f, 3.0f, 1.0f, 0.0f, 0.0f, 1.0f },  // MQ7
  { 3.0f, 1.0f, 0.0f, 1.0f, 0.0f, 0.0f, 1.0f },  // MQ6
  { 3.0f, 2.0f, 1.0f, 2.0f, 1.0f, 0.0f, 3.0f },  // MQ2
};

#endif
