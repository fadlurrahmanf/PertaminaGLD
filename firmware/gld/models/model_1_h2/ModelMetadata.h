#pragma once
#include <cstdint>
namespace pgl::gld::model {
constexpr const char* PROFILE_ID = "cnn-dualbranch-board-1-backup-h2-lpg-v1";
constexpr const char* SCALER_PROFILE_ID = "cnn-dualbranch-board-1-backup-h2-lpg-v1";
constexpr bool PRODUCTION_APPROVED = true; // Operator approved 2026-11-16; physical gas validation pending.
constexpr int EXPECTED_ADC_INPUT_ELEMENTS = 8;
constexpr int EXPECTED_EVIDENCE_INPUT_ELEMENTS = 7;
constexpr int EXPECTED_OUTPUT_ELEMENTS = 3;
constexpr uint8_t CLASS_MAP[EXPECTED_OUTPUT_ELEMENTS] = {0, 7, 1}; // Clean_Air, H2, LPG
}
